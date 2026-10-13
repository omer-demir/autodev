import asyncio
import hashlib
import io
import shutil
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from sqlmodel import Session, select

from .config import get_settings
from .database import engine
from .models import Task, WorkspaceRevision


class WorkspaceRevisionConflict(RuntimeError):
    pass


class SnapshotBackend:
    def put(self, key: str, content: bytes) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class LocalSnapshotBackend(SnapshotBackend):
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise RuntimeError(
                "Workspace snapshot key escapes the storage root")
        return path

    def put(self, key: str, content: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class AzureBlobSnapshotBackend(SnapshotBackend):
    def __init__(
        self,
        connection_string: str | None,
        container: str,
        account_url: str | None = None,
    ) -> None:
        if connection_string:
            service = BlobServiceClient.from_connection_string(
                connection_string)
        elif account_url:
            from azure.identity import DefaultAzureCredential

            service = BlobServiceClient(
                account_url=account_url,
                credential=DefaultAzureCredential(),
            )
        else:
            raise RuntimeError(
                "Azure Blob snapshots require a connection string or account URL"
            )
        self.container = service.get_container_client(container)
        try:
            self.container.create_container()
        except Exception as exc:
            from azure.core.exceptions import ResourceExistsError

            if not isinstance(exc, ResourceExistsError):
                raise

    def put(self, key: str, content: bytes) -> None:
        self.container.upload_blob(key, content, overwrite=False)

    def get(self, key: str) -> bytes:
        try:
            return self.container.download_blob(key).readall()
        except ResourceNotFoundError as exc:
            raise RuntimeError(
                f"Workspace snapshot is missing: {key}") from exc

    def delete(self, key: str) -> None:
        try:
            self.container.delete_blob(key)
        except ResourceNotFoundError:
            pass


def _pack(workspace: Path, max_bytes: int) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.add(workspace, arcname=".", recursive=True)
    content = buffer.getvalue()
    if len(content) > max_bytes:
        raise RuntimeError(f"Workspace snapshot exceeds {max_bytes} bytes")
    return content, hashlib.sha256(content).hexdigest()


def _restore(destination: Path, content: bytes, max_bytes: int) -> None:
    if len(content) > max_bytes:
        raise RuntimeError(f"Workspace snapshot exceeds {max_bytes} bytes")
    with TemporaryDirectory(prefix="autodev-snapshot-") as temporary:
        root = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            for member in archive.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise RuntimeError(
                        "Workspace snapshot contains an unsafe path")
                if member.issym() or member.islnk():
                    link = Path(member.linkname)
                    if link.is_absolute() or ".." in link.parts:
                        raise RuntimeError(
                            "Workspace snapshot contains an unsafe link")
            archive.extractall(root, filter="data")
        restored = root
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(restored), str(destination))


class WorkspaceSnapshotService:
    def __init__(self, backend: SnapshotBackend | None = None) -> None:
        settings = get_settings()
        if backend:
            self.backend = backend
        elif settings.workspace_snapshot_provider == "azure_blob":
            if not (
                settings.azure_storage_connection_string
                or settings.azure_storage_account_url
            ):
                raise RuntimeError(
                    "Azure Blob snapshots require WORKBENCH_AZURE_STORAGE_CONNECTION_STRING "
                    "or WORKBENCH_AZURE_STORAGE_ACCOUNT_URL"
                )
            self.backend = AzureBlobSnapshotBackend(
                settings.azure_storage_connection_string,
                settings.workspace_snapshot_container,
                settings.azure_storage_account_url,
            )
        elif settings.workspace_snapshot_provider == "local":
            self.backend = LocalSnapshotBackend(
                Path(settings.workspace_snapshot_dir))
        else:
            raise RuntimeError(
                f"Unknown workspace snapshot provider: {settings.workspace_snapshot_provider}"
            )
        self.max_bytes = settings.workspace_snapshot_max_bytes

    def latest(self, task_id: str) -> WorkspaceRevision | None:
        with Session(engine) as session:
            return session.exec(
                select(WorkspaceRevision)
                .where(WorkspaceRevision.task_id == task_id)
                .order_by(WorkspaceRevision.created_at.desc())
            ).first()

    def delete_task(self, task_id: str) -> None:
        with Session(engine) as session:
            revisions = session.exec(
                select(WorkspaceRevision).where(
                    WorkspaceRevision.task_id == task_id
                )
            ).all()
        for revision in revisions:
            self.backend.delete(revision.object_key)

    async def checkpoint(
        self,
        task_id: str,
        organization_id: str,
        workspace: Path,
        expected_parent: str | None,
    ) -> WorkspaceRevision:
        content, digest = await asyncio.to_thread(_pack, workspace, self.max_bytes)
        revision_id = f"REV-{uuid4().hex}"
        key = f"organizations/{organization_id}/tasks/{task_id}/revisions/{revision_id}.tar.gz"

        with Session(engine) as session:
            task_query = select(Task).where(Task.id == task_id)
            if engine.dialect.name == "postgresql":
                task_query = task_query.with_for_update()
            if not session.exec(task_query).first():
                raise RuntimeError(
                    f"Task not found for workspace checkpoint: {task_id}")
            latest = session.exec(
                select(WorkspaceRevision)
                .where(WorkspaceRevision.task_id == task_id)
                .order_by(WorkspaceRevision.created_at.desc())
            ).first()
            latest_id = latest.id if latest else None
            if latest_id != expected_parent:
                raise WorkspaceRevisionConflict(
                    f"Workspace revision changed from {expected_parent} to {latest_id}"
                )
            if latest and latest.digest == digest:
                return latest
            await asyncio.to_thread(self.backend.put, key, content)
            revision = WorkspaceRevision(
                id=revision_id,
                task_id=task_id,
                organization_id=organization_id,
                parent_id=latest_id,
                digest=digest,
                object_key=key,
                size_bytes=len(content),
            )
            session.add(revision)
            session.commit()
            session.refresh(revision)
            return revision

    async def restore_latest(
        self, task_id: str, destination: Path
    ) -> WorkspaceRevision | None:
        revision = self.latest(task_id)
        if not revision:
            return None
        content = await asyncio.to_thread(self.backend.get, revision.object_key)
        if hashlib.sha256(content).hexdigest() != revision.digest:
            raise RuntimeError(
                f"Workspace snapshot digest mismatch: {revision.id}")
        await asyncio.to_thread(_restore, destination, content, self.max_bytes)
        return revision


workspace_snapshots = WorkspaceSnapshotService()
