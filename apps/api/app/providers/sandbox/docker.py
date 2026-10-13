import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ...config import get_settings
from .provider import SandboxProvider


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

    async def _run(
        self,
        arguments: list[str],
        timeout: int = 180,
    ) -> subprocess.CompletedProcess[str]:
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
                "error": (
                    "Docker daemon socket is not mounted at /var/run/docker.sock "
                    "and DOCKER_HOST is unset."
                ),
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
            raise RuntimeError(
                result.stderr.strip(
                ) or f"Unable to prepare sandbox image {image}"
            )

    async def _host_path(self, workspace: str) -> str:
        settings = get_settings()
        workspace_root = os.path.realpath(settings.workspace_dir)
        if os.path.commonpath((workspace_root, workspace)) != workspace_root:
            raise RuntimeError(
                f"Sandbox workspace must be inside {workspace_root}")
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
            mount
            for mount in mounts
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
                "Docker sandbox workspace access must be read-only or read-write"
            )
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
                raise RuntimeError(
                    disconnected.stderr.strip() or "Unable to isolate sandbox network"
                )
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
            ["exec", "-i", session_id, "sh", "-lc", command],
            timeout=300,
        )
        return {
            "exit_code": result.returncode,
            "output": (result.stdout + result.stderr)[-100_000:],
            "simulated": False,
        }

    async def execute_args(
        self,
        session_id: str,
        arguments: list[str],
        *,
        network_access: bool = False,
    ) -> dict[str, Any]:
        command_timeout = get_settings().sandbox_command_timeout_seconds
        connected = False
        if network_access and self._network_modes.get(session_id, "none") == "none":
            connection = await self._run(["network", "connect", "bridge", session_id])
            if connection.returncode:
                raise RuntimeError(
                    connection.stderr.strip() or "Unable to enable dependency network"
                )
            connected = True
        try:
            result = await self._run(
                ["exec", "-i", session_id, *arguments],
                timeout=command_timeout,
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
