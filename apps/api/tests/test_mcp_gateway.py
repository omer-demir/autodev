from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Settings
from app.database import engine
from app.main import app
from app.models import Project, Task


_PROTOCOL_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


def _initialize(client: TestClient, **headers: str) -> dict[str, str]:
    response = client.post(
        "/gateway/mcp",
        headers={**_PROTOCOL_HEADERS, **headers},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
    )
    assert response.status_code == 200
    return {
        **_PROTOCOL_HEADERS,
        **headers,
        "mcp-session-id": response.headers["mcp-session-id"],
        "mcp-protocol-version": "2025-06-18",
    }


def test_streamable_http_lists_tenant_scoped_sessions_as_structured_data():
    suffix = uuid4().hex
    task_id = f"TASK-MCP-{suffix}"
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(name=f"MCP {suffix}",
                              repository_path=f"/tmp/{suffix}")
            session.add(project)
            session.commit()
            session.refresh(project)
            session.add(Task(
                id=task_id,
                project_id=project.id,
                title="MCP session",
                description="Verify standard MCP transport",
            ))
            session.commit()

        headers = _initialize(client)
        initialized = client.post(
            "/gateway/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        response = client.post(
            "/gateway/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "sessions.get", "arguments": {"task_id": task_id}},
            },
        )

    assert initialized.status_code == 202
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["id"] == task_id
    assert result["structuredContent"]["task"]["title"] == "MCP session"


def test_mcp_streamable_http_and_sse_require_authentication():
    oidc = Settings(
        auth_mode="oidc",
        oidc_issuer="https://identity.example",
        oidc_audience="autodev",
        oidc_jwks_url="https://identity.example/.well-known/jwks.json",
    )
    from unittest.mock import patch

    with patch("app.auth.get_settings", return_value=oidc), TestClient(app) as client:
        streamable = client.post(
            "/gateway/mcp",
            headers=_PROTOCOL_HEADERS,
            json={"jsonrpc": "2.0", "id": 1,
                  "method": "initialize", "params": {}},
        )
        sse = client.get("/gateway/sse")

    assert streamable.status_code == 401
    assert sse.status_code == 401
