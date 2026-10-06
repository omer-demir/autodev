from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from sqlmodel import Session
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.routing import Router

from .auth import Principal, current_principal
from .config import get_settings
from .database import engine
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


def _build_gateway() -> FastMCP:
    settings = get_settings()
    server = FastMCP(
        "Autodev Governed Sessions",
        instructions="Inspect and continue tenant-scoped Autodev sessions.",
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
