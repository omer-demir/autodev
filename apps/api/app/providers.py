import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

import httpx

from .config import get_settings
from .registry import RegistryError, get_definition


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class GovernanceDecision:
    decision: Decision
    agent_id: str
    action: str
    policy: str
    policy_version: str
    reason: str


class GovernanceProvider(ABC):
    @abstractmethod
    async def evaluate(
        self, agent_id: str, action: str, arguments: dict[str, Any], context: dict[str, Any]
    ) -> GovernanceDecision: ...

    @abstractmethod
    async def terminate(self, session_id: str, reason: str) -> None: ...


class LocalGovernanceProvider(GovernanceProvider):
    """Local default-deny governance boundary for agent tool execution."""

    allowed: ClassVar[set[str]] = {
        "repository.read", "repository.write", "filesystem.read", "filesystem.write",
        "test.run", "build.run", "dependency.install", "security.scan", "git.status", "git.diff",
    }
    approval: ClassVar[set[str]] = {
        "git.commit", "git.push", "pull_request.create"}

    async def evaluate(
        self, agent_id: str, action: str, arguments: dict[str, Any], context: dict[str, Any]
    ) -> GovernanceDecision:
        try:
            agent = get_definition(
                "agents", agent_id.removeprefix("did:local:"))["data"]
        except RegistryError:
            return GovernanceDecision(
                Decision.DENY, agent_id, action, "development-v1", "1.0",
                "Default-deny: agent identity is not registered",
            )
        policy_id = str(agent.get("policy", "development"))
        try:
            policy = get_definition("policies", policy_id)["data"]
        except RegistryError:
            return GovernanceDecision(
                Decision.DENY, agent_id, action, policy_id, "unknown",
                "Default-deny: agent governance policy is not registered",
            )
        policy_decision = str(policy.get("default_action", "deny"))
        for rule in policy.get("rules", []):
            if action in set(rule.get("capabilities", [])):
                policy_decision = str(rule["decision"])
                break
        policy_name = str(policy.get("name", policy_id))
        policy_version = str(policy.get("version", "unknown"))
        if action in set(agent.get("deny", [])) or policy_decision == "deny":
            decision, reason = Decision.DENY, "Capability is explicitly denied for this agent"
        elif action in set(agent.get("approval", [])) or policy_decision == "require_approval":
            decision, reason = Decision.REQUIRE_APPROVAL, "Agent capability requires human approval"
        elif action in set(agent.get("capabilities", [])) and policy_decision == "allow":
            decision, reason = Decision.ALLOW, "Capability granted by the agent declaration"
        else:
            decision, reason = Decision.DENY, "Default-deny: capability is not granted to this agent"
        return GovernanceDecision(
            decision, agent_id, action, policy_name, policy_version, reason
        )

    async def terminate(self, session_id: str, reason: str) -> None:
        return None


class AgentOSGovernanceProvider(GovernanceProvider):
    """Enforce the effective Workbench decision through Agent OS."""

    def __init__(self, local: GovernanceProvider | None = None) -> None:
        try:
            from agent_os.stateless import ExecutionContext, StatelessKernel
        except ImportError as exc:
            raise RuntimeError(
                "Agent OS governance is configured but agent-governance-toolkit-core "
                "is not installed"
            ) from exc
        self.local = local or LocalGovernanceProvider()
        self._context_type = ExecutionContext
        self._kernel_type = StatelessKernel

    async def evaluate(
        self, agent_id: str, action: str, arguments: dict[str, Any], context: dict[str, Any]
    ) -> GovernanceDecision:
        effective = await self.local.evaluate(agent_id, action, arguments, context)
        policy_id = "autodev-effective-policy"
        policy: dict[str, list[str]] = {}
        if effective.decision is Decision.DENY:
            policy["blocked_actions"] = [action]
        elif effective.decision is Decision.REQUIRE_APPROVAL:
            policy["require_approval"] = [action]

        try:
            kernel = self._kernel_type(policies={policy_id: policy})
            result = await kernel.execute(
                action=action,
                params=arguments,
                context=self._context_type(
                    agent_id=agent_id,
                    policies=[policy_id],
                    metadata=context,
                ),
            )
        except Exception as exc:
            return GovernanceDecision(
                Decision.DENY,
                agent_id,
                action,
                effective.policy,
                effective.policy_version,
                f"Agent OS enforcement failed closed: {type(exc).__name__}",
            )

        if result.success and effective.decision is Decision.ALLOW:
            return effective
        if not result.success and effective.decision is Decision.REQUIRE_APPROVAL:
            return effective
        reason = result.error or "Agent OS rejected the effective governance decision"
        return GovernanceDecision(
            Decision.DENY,
            agent_id,
            action,
            effective.policy,
            effective.policy_version,
            f"Agent OS denied the action: {reason}",
        )

    async def terminate(self, session_id: str, reason: str) -> None:
        await self.local.terminate(session_id, reason)


def get_governance_provider() -> GovernanceProvider:
    provider = get_settings().governance_provider.strip().lower()
    if provider == "local":
        return LocalGovernanceProvider()
    if provider == "agent_os":
        return AgentOSGovernanceProvider()
    raise RuntimeError(f"Unsupported governance provider: {provider}")


class SandboxProvider(ABC):
    @abstractmethod
    async def readiness(self) -> dict[str, Any]: ...

    @abstractmethod
    async def create(self, project: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, session_id: str,
                      command: str) -> dict[str, Any]: ...

    @abstractmethod
    async def execute_args(
        self, session_id: str, arguments: list[str], *, network_access: bool = False
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def kill(self, session_id: str) -> None: ...


class DockerSandboxProvider(SandboxProvider):
    """Disposable Docker boundary with no network or host credential mounts."""

    def __init__(self) -> None:
        self._network_modes: dict[str, str] = {}

    def executable(self) -> str:
        configured = get_settings().docker_executable
        resolved = shutil.which(configured)
        if not resolved:
            raise RuntimeError(
                f"Docker CLI '{configured}' is not available to the API process. "
                "Install the Docker CLI or set WORKBENCH_DOCKER_EXECUTABLE, then recreate "
                "the API container (a rebuilt image does not update an existing container)."
            )
        return resolved

    async def _run(self, arguments: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
        executable = self.executable()
        try:
            return await asyncio.to_thread(
                subprocess.run,
                [executable, *arguments],
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Docker CLI disappeared before execution ({executable}). Recreate the API "
                "container and verify WORKBENCH_DOCKER_EXECUTABLE."
            ) from exc

    async def readiness(self) -> dict[str, Any]:
        try:
            executable = self.executable()
        except RuntimeError as exc:
            return {"ready": False, "cli": False, "daemon": False, "error": str(exc)}
        socket = Path("/var/run/docker.sock")
        if not socket.exists() and not os.getenv("DOCKER_HOST"):
            return {
                "ready": False,
                "cli": True,
                "daemon": False,
                "executable": executable,
                "error": "Docker daemon socket is not mounted at /var/run/docker.sock and DOCKER_HOST is unset.",
            }
        result = await self._run(["version", "--format", "{{json .}}"], timeout=15)
        if result.returncode:
            return {
                "ready": False,
                "cli": True,
                "daemon": False,
                "executable": executable,
                "error": (result.stderr or result.stdout).strip(),
            }
        return {
            "ready": True,
            "cli": True,
            "daemon": True,
            "executable": executable,
        }

    async def ensure_image(self, image: str) -> None:
        settings = get_settings()
        inspect = await self._run(["image", "inspect", image])
        if inspect.returncode == 0:
            return
        if image == settings.sandbox_image:
            result = await self._run(
                ["build", "-t", image, "-f", "docker/sandbox/Dockerfile", "."],
                timeout=600,
            )
        else:
            result = await self._run(["pull", image], timeout=600)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()
                               or f"Unable to prepare sandbox image {image}")

    async def _host_path(self, workspace: str) -> str:
        settings = get_settings()
        workspace_root = os.path.realpath(settings.workspace_dir)
        if os.path.commonpath((workspace_root, workspace)) != workspace_root:
            raise RuntimeError(
                f"Sandbox workspace must be inside {workspace_root}"
            )
        if settings.docker_workspace_host:
            relative = os.path.relpath(workspace, workspace_root)
            return os.path.join(settings.docker_workspace_host, relative)

        inspect = await self._run(["inspect", os.environ.get("HOSTNAME", "")])
        if inspect.returncode:
            raise RuntimeError(
                "Unable to map the task worktree to a Docker host path. "
                "Set WORKBENCH_DOCKER_WORKSPACE_HOST."
            )
        try:
            mounts = json.loads(inspect.stdout)[0]["Mounts"]
        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            raise RuntimeError(
                "Unable to parse Docker mounts for the control-plane container. "
                "Set WORKBENCH_DOCKER_WORKSPACE_HOST."
            ) from None
        candidates = [
            mount for mount in mounts
            if workspace == mount["Destination"]
            or workspace.startswith(f'{mount["Destination"].rstrip("/")}/')
        ]
        if not candidates:
            raise RuntimeError(
                "The task worktree is not backed by a Docker host mount. "
                "Set WORKBENCH_DOCKER_WORKSPACE_HOST."
            )
        mount = max(candidates, key=lambda item: len(item["Destination"]))
        relative = os.path.relpath(workspace, mount["Destination"])
        if relative == ".":
            return mount["Source"]
        source = mount["Source"].rstrip("/\\")
        return f"{source}/{relative}"

    async def create(self, project: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        image = str(project.get("image") or settings.sandbox_image)
        network_mode = str(project.get("network_mode") or "none")
        workspace_access = str(project.get("workspace_access") or "read-write")
        if network_mode not in {"none", "bridge"}:
            raise RuntimeError(
                "Docker sandbox network mode must be none or bridge")
        if workspace_access not in {"read-only", "read-write"}:
            raise RuntimeError(
                "Docker sandbox workspace access must be read-only or read-write")
        await self.ensure_image(image)
        name = project["name"]
        workspace = os.path.realpath(project["workspace"])
        mount_source = await self._host_path(workspace)
        await self._run(["rm", "-f", name])
        result = await self._run([
            "run", "-d", "--name", name,
            "--network", "bridge", "--memory", "2g", "--cpus", "2",
            "--pids-limit", "256", "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL", "--user", f"{os.getuid()}:{os.getgid()}",
            "--env", "HOME=/tmp", "--workdir", "/workspace/project",
            "--mount", (
                f"type=bind,src={mount_source},dst=/workspace/project"
                f"{',readonly' if workspace_access == 'read-only' else ''}"
            ),
            image, "sleep", "infinity",
        ])
        if result.returncode:
            raise RuntimeError(result.stderr.strip()
                               or "Unable to create sandbox")
        container_id = result.stdout.strip()
        if network_mode == "none":
            disconnected = await self._run(
                ["network", "disconnect", "-f", "bridge", container_id]
            )
            if disconnected.returncode:
                await self._run(["rm", "-f", container_id])
                raise RuntimeError(disconnected.stderr.strip()
                                   or "Unable to isolate sandbox network")
        self._network_modes[container_id] = network_mode
        return {
            "container_id": container_id,
            "provider": "docker",
            "status": "READY",
            "workspace": "/workspace/project",
            "network_policy": network_mode,
            "image": image,
        }

    async def execute(self, session_id: str, command: str) -> dict[str, Any]:
        result = await self._run(
            ["exec", "-i", session_id, "sh", "-lc", command], timeout=300
        )
        return {
            "exit_code": result.returncode,
            "output": (result.stdout + result.stderr)[-100_000:],
            "simulated": False,
        }

    async def execute_args(
        self, session_id: str, arguments: list[str], *, network_access: bool = False
    ) -> dict[str, Any]:
        command_timeout = get_settings().sandbox_command_timeout_seconds
        connected = False
        if network_access and self._network_modes.get(session_id, "none") == "none":
            connection = await self._run(["network", "connect", "bridge", session_id])
            if connection.returncode:
                raise RuntimeError(connection.stderr.strip()
                                   or "Unable to enable dependency network")
            connected = True
        try:
            result = await self._run(
                ["exec", "-i", session_id, *arguments], timeout=command_timeout
            )
        finally:
            if connected:
                disconnection = await self._run(
                    ["network", "disconnect", "-f", "bridge", session_id]
                )
                if disconnection.returncode:
                    raise RuntimeError(
                        disconnection.stderr.strip()
                        or "Unable to restore sandbox network isolation"
                    )
        return {
            "exit_code": result.returncode,
            "output": (result.stdout + result.stderr)[-100_000:],
            "simulated": False,
        }

    async def kill(self, session_id: str) -> None:
        result = await self._run(["rm", "-f", session_id])
        self._network_modes.pop(session_id, None)
        if result.returncode and "No such container" not in result.stderr:
            raise RuntimeError(result.stderr.strip())


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
        for path in sorted(workspace.rglob("*"), key=lambda item: str(item.relative_to(workspace))):
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
        self, identifier: str, active: dict[str, Any]
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
        self, identifier: str, active: dict[str, Any]
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
                    "POST", "/.management/stopSession", identifier, management=True, timeout=30
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
        self, session_id: str, arguments: list[str], *, network_access: bool = False
    ) -> dict[str, Any]:
        if network_access and self.network_mode != "bridge":
            raise RuntimeError(
                "The configured Azure session pool does not permit network access")
        return await self._execute(session_id, arguments)

    async def _execute(self, session_id: str, arguments: list[str]) -> dict[str, Any]:
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
            "output": (str(result.get("stdout", "")) + str(result.get("stderr", "")))[-100_000:],
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
                "POST", "/.management/stopSession", session_id, management=True, timeout=30
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            self._sessions.pop(session_id, None)
        if errors:
            raise ExceptionGroup(
                f"Failed to terminate Azure session {session_id}", errors)


@lru_cache
def get_sandbox_provider() -> SandboxProvider:
    settings = get_settings()
    provider = settings.sandbox_provider.strip().lower()
    if provider == "docker":
        return DockerSandboxProvider()
    if provider in {"azure", "azure-container-apps-session-pool"}:
        if not settings.azure_session_pool_endpoint:
            raise RuntimeError(
                "Azure sandbox is configured but WORKBENCH_AZURE_SESSION_POOL_ENDPOINT is unset"
            )
        return AzureContainerAppsSessionProvider(
            endpoint=settings.azure_session_pool_endpoint,
            network_mode=settings.azure_session_pool_network_mode,
            pool_profile=settings.azure_session_pool_profile,
            cpu_limit=settings.azure_session_pool_cpu_limit,
            memory_mb=settings.azure_session_pool_memory_mb,
        )
    raise RuntimeError(
        f"Unsupported sandbox provider: {settings.sandbox_provider}")
