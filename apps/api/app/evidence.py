import json
import shutil
from pathlib import Path
from typing import Any

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContainerClient

from .config import get_settings


class EvidenceProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self.root = Path(settings.evidence_dir)
        self.container: ContainerClient | None = None
        if settings.evidence_provider == "azure_blob":
            if settings.azure_storage_connection_string:
                service = BlobServiceClient.from_connection_string(
                    settings.azure_storage_connection_string
                )
            elif settings.azure_storage_account_url:
                from azure.identity import DefaultAzureCredential

                service = BlobServiceClient(
                    account_url=settings.azure_storage_account_url,
                    credential=DefaultAzureCredential(),
                )
            else:
                raise RuntimeError(
                    "Azure Blob evidence requires a connection string or account URL"
                )
            self.container = service.get_container_client(
                settings.evidence_container)
            try:
                self.container.create_container()
            except ResourceExistsError:
                pass
        elif settings.evidence_provider != "local":
            raise RuntimeError(
                f"Unknown evidence provider: {settings.evidence_provider}"
            )

    def write(self, task_id: str, name: str, content: Any) -> None:
        serialized = json.dumps(content, indent=2, default=str)
        if self.container:
            self.container.upload_blob(
                f"tasks/{task_id}/{name}.json",
                serialized.encode(),
                overwrite=True,
            )
            return
        directory = self.root / task_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{name}.json").write_text(
            serialized, encoding="utf-8"
        )

    def bundle(self, task_id: str) -> dict[str, Any]:
        if self.container:
            prefix = f"tasks/{task_id}/"
            return {
                Path(blob.name).stem: json.loads(
                    self.container.download_blob(blob.name).readall()
                )
                for blob in self.container.list_blobs(name_starts_with=prefix)
                if blob.name.endswith(".json")
            }
        directory = self.root / task_id
        if not directory.exists():
            return {}
        return {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        }

    def delete_task(self, task_id: str) -> None:
        if self.container:
            prefix = f"tasks/{task_id}/"
            for blob in self.container.list_blobs(name_starts_with=prefix):
                self.container.delete_blob(blob.name)
            return
        shutil.rmtree(self.root / task_id, ignore_errors=True)


evidence_provider = EvidenceProvider()
