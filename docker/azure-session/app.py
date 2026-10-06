import asyncio
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field


MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_OUTPUT_BYTES = 100_000
WORKSPACE = Path(os.getenv("AUTODEV_WORKSPACE",
                 "/workspace/project")).resolve()
SANDBOX_UID = int(os.getenv("AUTODEV_SANDBOX_UID", "10001"))
SANDBOX_GID = int(os.getenv("AUTODEV_SANDBOX_GID", "10001"))
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
SENSITIVE_ENVIRONMENT = re.compile(
    r"TOKEN|PASSWORD|SECRET|CREDENTIAL|PRIVATE|API_KEY", re.IGNORECASE
)

app = FastAPI(title="Autodev Azure Session", docs_url=None, redoc_url=None)
workspace_access = "read-write"
command_environment: dict[str, str] = {}


class ExecuteRequest(BaseModel):
    command: list[str] = Field(min_length=1, max_length=128)
    timeoutMs: int = Field(default=300_000, ge=100, le=1_800_000)


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = Path(member.name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or (path.parts and path.parts[0] == ".git")
            or member.issym()
            or member.islnk()
            or member.isdev()
        ):
            raise HTTPException(
                400, "Workspace archive contains an unsafe path")
    return members


def _replace_workspace(content: bytes, access: str) -> None:
    if len(content) > MAX_ARCHIVE_BYTES:
        raise HTTPException(413, "Workspace archive is too large")
    with tempfile.TemporaryDirectory(prefix="autodev-import-") as temporary:
        target = Path(temporary)
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
                archive.extractall(
                    target, members=_safe_members(archive), filter="data")
        except tarfile.TarError as exc:
            raise HTTPException(400, "Workspace archive is invalid") from exc
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        for path in WORKSPACE.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for path in target.iterdir():
            shutil.move(str(path), WORKSPACE / path.name)
    writable = access == "read-write"
    for path in [WORKSPACE, *WORKSPACE.rglob("*")]:
        if os.geteuid() == 0:
            os.chown(path, SANDBOX_UID, SANDBOX_GID, follow_symlinks=False)
        if path.is_dir():
            path.chmod(0o750 if writable else 0o550)
        elif path.is_file():
            path.chmod(0o640 if writable else 0o440)


def _archive_workspace() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in WORKSPACE.rglob("*"):
            archive.add(path, arcname=str(
                path.relative_to(WORKSPACE)), recursive=False)
    content = buffer.getvalue()
    if len(content) > MAX_ARCHIVE_BYTES:
        raise HTTPException(413, "Workspace archive is too large")
    return content


def _parse_environment(raw: str) -> dict[str, str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            400, "Session environment header is invalid") from exc
    if not isinstance(value, dict) or len(value) > 100:
        raise HTTPException(400, "Session environment must be an object")
    environment: dict[str, str] = {}
    for name, content in value.items():
        if (
            not isinstance(name, str)
            or not ENVIRONMENT_NAME.fullmatch(name)
            or SENSITIVE_ENVIRONMENT.search(name)
            or not isinstance(content, str)
            or len(content) > 4096
        ):
            raise HTTPException(
                400, "Session environment contains an unsafe entry")
        environment[name] = content
    return environment


@app.get("/health")
@app.get("/ready")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/workspace/import", status_code=204)
async def import_workspace(
    request: Request,
    x_autodev_workspace_access: str = Header(default="read-write"),
    x_autodev_environment: str = Header(default="{}"),
) -> Response:
    global workspace_access, command_environment
    if x_autodev_workspace_access not in {"read-only", "read-write"}:
        raise HTTPException(
            400, "Workspace access must be read-only or read-write")
    content = await request.body()
    environment = _parse_environment(x_autodev_environment)
    await asyncio.to_thread(_replace_workspace, content, x_autodev_workspace_access)
    workspace_access = x_autodev_workspace_access
    command_environment = environment
    return Response(status_code=204)


@app.get("/workspace/export")
async def export_workspace() -> Response:
    content = await asyncio.to_thread(_archive_workspace)
    return Response(content, media_type="application/gzip")


@app.post("/execute")
async def execute(payload: ExecuteRequest) -> dict[str, object]:
    if not WORKSPACE.is_dir():
        raise HTTPException(409, "Workspace has not been imported")
    environment = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": f"/home/{os.getenv('AUTODEV_SANDBOX_USER', 'sandbox')}",
        "LANG": "C.UTF-8",
        **command_environment,
    }
    child_setup = None
    if os.geteuid() == 0:
        def child_setup() -> None:
            os.setgid(SANDBOX_GID)
            os.setuid(SANDBOX_UID)

    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *payload.command,
            cwd=WORKSPACE,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=child_setup,
        )
    except FileNotFoundError:
        return {
            "exitCode": 127,
            "stdout": "",
            "stderr": f"Command not found: {payload.command[0]}\n",
            "durationMs": round((time.monotonic() - started) * 1000),
            "truncated": False,
        }
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=payload.timeoutMs / 1000
        )
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        stderr += b"Command timed out\n"
        exit_code = 124
    else:
        exit_code = process.returncode
    truncated = len(stdout) + len(stderr) > MAX_OUTPUT_BYTES
    if truncated:
        allowance = MAX_OUTPUT_BYTES // 2
        stdout, stderr = stdout[-allowance:], stderr[-allowance:]
    return {
        "exitCode": exit_code,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "durationMs": round((time.monotonic() - started) * 1000),
        "truncated": truncated,
    }
