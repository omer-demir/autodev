import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from ...config import get_settings
from .provider import SandboxProvider

_DYNAMIC_SESSIONS_SCOPE = "https://dynamicsessions.io/.default"
_SESSION_API_VERSION = "2025-02-02-preview"
_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


class AzureContainerAppsSessionProvider(SandboxProvider):
    """Remote Hyper-V sandbox backed by an Azure Container Apps session pool."""

    def __init__(
        self,
        *,
        endpoint: str,
        network_mode: str,
        pool_profile: str,
        cpu_limit: float,
        memory_mb: int,
        token_provider: Callable[[], Awaitable[str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized = endpoint.rstrip("/")
        if not normalized.startswith("https://"):
            raise RuntimeError("Azure session pool endpoint must use HTTPS")
        if network_mode not in {"none", "bridge"}:
            raise RuntimeError(
                "Azure session pool network mode must be none or bridge")
        self.endpoint = normalized
        self.network_mode = network_mode
        self.pool_profile = pool_profile
        self.cpu_limit = cpu_limit
        self.memory_mb = memory_mb
        self._token_provider = token_provider or self._azure_token
        self._client = client or httpx.AsyncClient(timeout=120)
        self._sessions: dict[str, dict[str, Any]] = {}

    async def readiness(self) -> dict[str, Any]:
        try:
            token = await self._token_provider()
        except Exception as exc:
            return {
                "ready": False,
                "provider": "azure-container-apps-session-pool",
                "endpoint": self.endpoint,
                "error": str(exc),
            }
        return {
            "ready": bool(token),
            "provider": "azure-container-apps-session-pool",
            "endpoint": self.endpoint,
            "network_policy": self.network_mode,
            "image": self.pool_profile,
        }

    async def _azure_token(self) -> str:
        try:
            from azure.identity.aio import DefaultAzureCredential
        except ImportError as exc:
            raise RuntimeError(
                "Azure sandbox is configured but azure-identity is not installed"
            ) from exc
        credential = DefaultAzureCredential()
        try:
            token = await credential.get_token(_DYNAMIC_SESSIONS_SCOPE)
        finally:
            await credential.close()
        if not token.token:
            raise RuntimeError(
                "Unable to acquire an Azure dynamic-session token")
        return token.token

    async def _request(
        self,
        method: str,
        path: str,
        identifier: str,
        *,
        content: bytes | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 120,
        management: bool = False,
    ) -> httpx.Response:
        token = await self._token_provider()
        params = {"identifier": identifier}
        if management:
            params["api-version"] = _SESSION_API_VERSION
        response = await self._client.request(
            method,
            f"{self.endpoint}{path}",
            params=params,
            content=content,
            json=json_body,
            headers={"Authorization": f"Bearer {token}", **(headers or {})},
            timeout=timeout,
        )
        if response.is_error:
            detail = response.text[:4096]
            raise RuntimeError(
                f"Azure session request {path} failed: HTTP {response.status_code}"
                f"{': ' + detail if detail else ''}"
            )
        return response

    @staticmethod
    def _pack_workspace(workspace: Path) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for path in workspace.rglob("*"):
                relative = path.relative_to(workspace)
                if relative.parts and relative.parts[0] == ".git":
                    continue
                archive.add(path, arcname=str(relative), recursive=False)
        value = buffer.getvalue()
        if len(value) > _MAX_ARCHIVE_BYTES:
            raise RuntimeError(
                f"Workspace archive exceeds {_MAX_ARCHIVE_BYTES} bytes")
        return value

    @staticmethod
    def _workspace_fingerprint(workspace: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(
            workspace.rglob("*"),
            key=lambda item: str(item.relative_to(workspace)),
        ):
            relative = path.relative_to(workspace)
            if relative.parts and relative.parts[0] == ".git":
                continue
            digest.update(str(relative).encode())
            if path.is_symlink():
                digest.update(b"L")
                digest.update(os.readlink(path).encode())
            elif path.is_dir():
                digest.update(b"D")
            elif path.is_file():
                digest.update(b"F")
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
        return digest.hexdigest()

    async def _import_workspace(
        self,
        identifier: str,
        active: dict[str, Any],
    ) -> None:
        workspace = Path(active["workspace"])
        before = self._workspace_fingerprint(workspace)
        archive = self._pack_workspace(workspace)
        after = self._workspace_fingerprint(workspace)
        if before != after:
            raise RuntimeError(
                "Host workspace changed while preparing Azure synchronization")
        await self._request(
            "POST",
            "/workspace/import",
            identifier,
            content=archive,
            headers={
                "Content-Type": "application/gzip",
                "X-Autodev-Workspace-Access": active["workspace_access"],
                "X-Autodev-Environment": active["environment"],
            },
        )
        active["host_fingerprint"] = after
        active["remote_dirty"] = False

    async def _export_workspace(
        self,
        identifier: str,
        active: dict[str, Any],
    ) -> None:
        workspace = Path(active["workspace"])
        expected = active["host_fingerprint"]
        if self._workspace_fingerprint(workspace) != expected:
            active["remote_dirty"] = False
            raise RuntimeError(
                "Host workspace changed during Azure execution; remote export was not applied"
            )
        response = await self._request("GET", "/workspace/export", identifier)
        if self._workspace_fingerprint(workspace) != expected:
            active["remote_dirty"] = False
            raise RuntimeError(
                "Host workspace changed during Azure export; remote export was not applied"
            )
        self._restore_workspace(workspace, response.content)
        active["host_fingerprint"] = self._workspace_fingerprint(workspace)
        active["remote_dirty"] = False

    @staticmethod
    def _restore_workspace(workspace: Path, content: bytes) -> None:
        if len(content) > _MAX_ARCHIVE_BYTES:
            raise RuntimeError(
                f"Workspace archive exceeds {_MAX_ARCHIVE_BYTES} bytes")
        with tempfile.TemporaryDirectory(prefix="autodev-azure-export-") as temporary:
            target = Path(temporary)
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
                for member in archive.getmembers():
                    member_path = Path(member.name)
                    if (
                        member_path.is_absolute()
                        or ".." in member_path.parts
                        or (member_path.parts and member_path.parts[0] == ".git")
                        or member.issym()
                        or member.islnk()
                    ):
                        raise RuntimeError(
                            "Azure workspace export contains an unsafe path")
                archive.extractall(target, filter="data")
            for path in workspace.iterdir():
                if path.name == ".git":
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            for path in target.iterdir():
                shutil.move(str(path), workspace / path.name)

    async def create(self, project: dict[str, Any]) -> dict[str, Any]:
        requested_network = str(project.get(
            "network_mode") or self.network_mode)
        requested_profile = str(project.get(
            "pool_profile") or self.pool_profile)
        if requested_network != self.network_mode:
            raise RuntimeError(
                f"Azure session pool network mode is {self.network_mode}, "
                f"but the workload requires {requested_network}"
            )
        if requested_profile != self.pool_profile:
            raise RuntimeError(
                f"Azure session pool profile is {self.pool_profile}, "
                f"but the workload requires {requested_profile}"
            )
        workspace = Path(str(project["workspace"])).resolve()
        if not workspace.is_dir():
            raise RuntimeError("Sandbox workspace must be a directory")
        identifier = str(uuid.uuid4())
        active: dict[str, Any] = {
            "workspace": str(workspace),
            "workspace_access": str(project.get("workspace_access") or "read-write"),
            "environment": json.dumps(project.get("environment") or {}),
            "host_fingerprint": "",
            "remote_dirty": False,
        }
        try:
            await self._import_workspace(identifier, active)
        except Exception as import_error:
            try:
                await self._request(
                    "POST",
                    "/.management/stopSession",
                    identifier,
                    management=True,
                    timeout=30,
                )
            except Exception as cleanup_error:
                raise ExceptionGroup(
                    "Azure workspace import and session cleanup failed",
                    [import_error, cleanup_error],
                ) from import_error
            raise
        self._sessions[identifier] = active
        return {
            "container_id": identifier,
            "provider": "azure-container-apps-session-pool",
            "status": "READY",
            "workspace": "/workspace/project",
            "network_policy": requested_network,
            "image": self.pool_profile,
        }

    async def execute(self, session_id: str, command: str) -> dict[str, Any]:
        return await self._execute(session_id, ["sh", "-lc", command])

    async def execute_args(
        self,
        session_id: str,
        arguments: list[str],
        *,
        network_access: bool = False,
    ) -> dict[str, Any]:
        if network_access and self.network_mode != "bridge":
            raise RuntimeError(
                "The configured Azure session pool does not permit network access"
            )
        return await self._execute(session_id, arguments)

    async def _execute(
        self,
        session_id: str,
        arguments: list[str],
    ) -> dict[str, Any]:
        active = self._sessions.get(session_id)
        if not active:
            raise RuntimeError(
                f"Unknown Azure Container Apps session: {session_id}")
        await self._import_workspace(session_id, active)
        timeout = get_settings().sandbox_command_timeout_seconds
        active["remote_dirty"] = True
        response = await self._request(
            "POST",
            "/execute",
            session_id,
            json_body={"command": arguments, "timeoutMs": timeout * 1000},
            timeout=timeout + 10,
        )
        result = response.json()
        if active["workspace_access"] == "read-write":
            await self._export_workspace(session_id, active)
        return {
            "exit_code": int(result.get("exitCode", 1)),
            "output": (
                str(result.get("stdout", "")) + str(result.get("stderr", ""))
            )[-100_000:],
            "simulated": False,
        }

    async def kill(self, session_id: str) -> None:
        active = self._sessions.get(session_id)
        if not active:
            return
        errors: list[Exception] = []
        if active["workspace_access"] == "read-write" and active["remote_dirty"]:
            try:
                await self._export_workspace(session_id, active)
            except Exception as exc:
                errors.append(exc)
        try:
            await self._request(
                "POST",
                "/.management/stopSession",
                session_id,
                management=True,
                timeout=30,
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            self._sessions.pop(session_id, None)
        if errors:
            raise ExceptionGroup(
                f"Failed to terminate Azure session {session_id}", errors)
