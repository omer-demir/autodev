import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from sqlmodel import Session, select
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.routing import Router

from .auth import Principal, current_principal
from .config import get_settings
from .database import engine
from .execution_queue import ExecutionConflict, enqueue_execution
from .models import ExecutionJob, Task
from .session_service import (
    SessionServiceError,
    continue_durable_session,
    get_durable_session,
    list_durable_sessions,
)


def _principal(context: Context, permission: str) -> Principal:
    request = context.request_context.request
    principal = getattr(getattr(request, "state", None), "principal", None)
    if not isinstance(principal, Principal):
        raise PermissionError("Authenticated MCP request context is required")
    if not principal.can(permission):
        raise PermissionError(
            f"Role {principal.role} cannot perform {permission}")
    return principal


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


async def list_sessions(context: Context, limit: int = 50) -> dict[str, Any]:
    principal = _principal(context, "read")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    with Session(engine) as session:
        values = list_durable_sessions(session, principal)[:limit]
    return {"sessions": _json_value(values)}


async def get_session(context: Context, task_id: str) -> dict[str, Any]:
    principal = _principal(context, "read")
    try:
        with Session(engine) as session:
            return _json_value(get_durable_session(session, task_id, principal))
    except SessionServiceError as exc:
        raise ValueError(exc.detail) from exc


async def continue_session(
    context: Context,
    task_id: str,
    content: str,
    agent_id: str | None = None,
) -> dict[str, Any]:
    principal = _principal(context, "task.operate")
    if not content.strip() or len(content) > 20_000:
        raise ValueError("content must contain between 1 and 20000 characters")
    try:
        with Session(engine) as session:
            return await continue_durable_session(
                session, task_id, content, agent_id, principal
            )
    except SessionServiceError as exc:
        raise ValueError(exc.detail) from exc


async def _invoke_workspace_tool(
    context: Context,
    task_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    principal = _principal(context, "sandbox.operate")
    with Session(engine) as session:
        task = session.exec(select(Task).where(
            Task.id == task_id,
            Task.organization_id == principal.organization_id,
        )).first()
    if not task:
        raise ValueError("Session not found")

    payload = {"tool": tool, "arguments": arguments}
    try:
        job = enqueue_execution(task_id, "tool", payload)
    except ExecutionConflict as exc:
        raise ValueError(str(exc)) from exc

    deadline = time.monotonic() + get_settings().sandbox_command_timeout_seconds + 30
    while time.monotonic() < deadline:
        with Session(engine) as session:
            current = session.get(ExecutionJob, job.id)
            if not current:
                raise RuntimeError("Workspace tool execution disappeared")
            if current.status == "DONE":
                return {
                    "execution_job_id": current.id,
                    **(current.result or {}),
                }
            if current.status in {"FAILED", "CANCELLED"}:
                raise RuntimeError(
                    current.error or f"Workspace tool execution {current.status.lower()}"
                )
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Workspace tool execution timed out: {job.id}")


async def list_workspace_files(
    context: Context,
    task_id: str,
    path: str = ".",
    pattern: str = "*",
    offset: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    return await _invoke_workspace_tool(
        context,
        task_id,
        "list_files",
        {"path": path, "pattern": pattern, "offset": offset, "limit": limit},
    )


async def search_workspace_text(
    context: Context,
    task_id: str,
    query: str,
    path: str = ".",
    pattern: str = "*",
    max_matches: int = 50,
) -> dict[str, Any]:
    return await _invoke_workspace_tool(
        context,
        task_id,
        "search_text",
        {
            "query": query,
            "path": path,
            "pattern": pattern,
            "max_matches": max_matches,
        },
    )


async def read_workspace_file(
    context: Context,
    task_id: str,
    path: str,
    offset: int = 0,
    limit: int = 6000,
) -> dict[str, Any]:
    return await _invoke_workspace_tool(
        context,
        task_id,
        "read_file",
        {"path": path, "offset": offset, "limit": limit},
    )


async def write_workspace_file(
    context: Context,
    task_id: str,
    path: str,
    content: str,
) -> dict[str, Any]:
    return await _invoke_workspace_tool(
        context,
        task_id,
        "write_file",
        {"path": path, "content": content},
    )


async def delete_workspace_file(
    context: Context,
    task_id: str,
    path: str,
) -> dict[str, Any]:
    return await _invoke_workspace_tool(
        context,
        task_id,
        "delete_file",
        {"path": path},
    )


async def run_workspace_command(
    context: Context,
    task_id: str,
    arguments: list[str],
) -> dict[str, Any]:
    if not arguments or len(arguments) > 100:
        raise ValueError("arguments must contain between 1 and 100 values")
    return await _invoke_workspace_tool(
        context,
        task_id,
        "run_command",
        {"arguments": arguments},
    )


def _build_gateway() -> FastMCP:
    settings = get_settings()
    server = FastMCP(
        "Autodev Governed Sessions",
        instructions=(
            "Inspect and continue tenant-scoped Autodev sessions, and use governed "
            "workspace tools for repository operations."
        ),
        streamable_http_path="/mcp",
        sse_path="/sse",
        message_path="/messages",
        json_response=True,
        max_request_body_size=1024 * 1024,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                item.strip() for item in settings.mcp_allowed_hosts.split(",") if item.strip()
            ],
            allowed_origins=[
                item.strip() for item in settings.mcp_allowed_origins.split(",") if item.strip()
            ],
        ),
    )
    server.add_tool(list_sessions, name="sessions.list",
                    structured_output=True)
    server.add_tool(get_session, name="sessions.get", structured_output=True)
    server.add_tool(continue_session, name="sessions.continue",
                    structured_output=True)
    server.add_tool(list_workspace_files, name="workspace.list_files",
                    structured_output=True)
    server.add_tool(search_workspace_text, name="workspace.search_text",
                    structured_output=True)
    server.add_tool(read_workspace_file, name="workspace.read_file",
                    structured_output=True)
    server.add_tool(write_workspace_file, name="workspace.write_file",
                    structured_output=True)
    server.add_tool(delete_workspace_file, name="workspace.delete_file",
                    structured_output=True)
    server.add_tool(run_workspace_command, name="workspace.run_command",
                    structured_output=True)
    return server


_transport_router: Router | None = None


class AuthenticatedMCPGateway:
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            try:
                with Session(engine) as session:
                    principal = current_principal(
                        HTTPConnection(scope), session)
                scope.setdefault("state", {})["principal"] = principal
            except HTTPException as exc:
                await JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code
                )(scope, receive, send)
                return
        if _transport_router is None:
            await JSONResponse(
                {"detail": "MCP gateway is not ready"}, status_code=503
            )(scope, receive, send)
            return
        await _transport_router(scope, receive, send)


mcp_gateway_app = AuthenticatedMCPGateway()


@asynccontextmanager
async def mcp_gateway_lifespan() -> AsyncIterator[None]:
    global _transport_router
    server = _build_gateway()
    streamable_app = server.streamable_http_app()
    sse_app = server.sse_app()
    _transport_router = Router(
        routes=[*streamable_app.routes, *sse_app.routes])
    try:
        async with streamable_app.router.lifespan_context(streamable_app):
            yield
    finally:
        _transport_router = None
