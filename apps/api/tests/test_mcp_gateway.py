from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session

from app.config import Settings
from app.auth import Principal
from app.database import engine
from app.main import app
from app.models import ExecutionJob, Project, Task
from app.mcp_gateway import _principal


_PROTOCOL_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        ("viewer", "read", True),
        ("viewer", "task.operate", False),
        ("viewer", "sandbox.operate", False),
        ("developer", "read", True),
        ("developer", "task.operate", True),
        ("developer", "sandbox.operate", True),
        ("reviewer", "read", True),
        ("reviewer", "task.operate", False),
        ("reviewer", "sandbox.operate", False),
        ("admin", "read", True),
        ("admin", "task.operate", True),
        ("admin", "sandbox.operate", True),
    ],
)
def test_mcp_role_permission_matrix(role: str, permission: str, allowed: bool):
    context = SimpleNamespace(request_context=SimpleNamespace(
        request=SimpleNamespace(state=SimpleNamespace(
            principal=Principal(f"{role}-user", "local", role)
        ))
    ))

    if allowed:
        assert _principal(context, permission).role == role
    else:
        with pytest.raises(PermissionError):
            _principal(context, permission)


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


def test_streamable_http_exposes_governed_workspace_tools():
    with TestClient(app) as client:
        headers = _initialize(client)
        client.post(
            "/gateway/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        response = client.post(
            "/gateway/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )

    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {
        "workspace.list_files",
        "workspace.search_text",
        "workspace.read_file",
        "workspace.write_file",
        "workspace.delete_file",
        "workspace.run_command",
    } <= names


def test_workspace_tool_returns_durable_worker_result():
    suffix = uuid4().hex
    task_id = f"TASK-MCP-TOOL-{suffix}"
    job_id = f"JOB-{suffix}"
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"MCP tool {suffix}", repository_path=f"/tmp/{suffix}")
            session.add(project)
            session.commit()
            session.refresh(project)
            session.add(Task(
                id=task_id,
                project_id=project.id,
                title="MCP tool session",
                description="Return a durable worker result",
            ))
            session.add(ExecutionJob(
                id=job_id,
                task_id=task_id,
                operation="tool",
                status="DONE",
                payload={"tool": "read_file", "arguments": {
                    "path": "README.md", "offset": 0, "limit": 6000}},
                result={"path": "README.md", "content": "governed"},
            ))
            session.commit()

        headers = _initialize(client)
        client.post(
            "/gateway/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        with patch("app.mcp_gateway.enqueue_execution") as enqueue:
            enqueue.return_value = ExecutionJob(
                id=job_id,
                task_id=task_id,
                operation="tool",
                status="DONE",
                payload={"tool": "read_file", "arguments": {
                    "path": "README.md", "offset": 0, "limit": 6000}},
            )
            response = client.post(
                "/gateway/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "workspace.read_file",
                        "arguments": {"task_id": task_id, "path": "README.md"},
                    },
                },
            )

    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == {
        "execution_job_id": job_id,
        "path": "README.md",
        "content": "governed",
    }


def test_mcp_streamable_http_and_sse_require_authentication():
    oidc = Settings(
        auth_mode="oidc",
        oidc_issuer="https://identity.example",
        oidc_audience="autodev",
        oidc_jwks_url="https://identity.example/.well-known/jwks.json",
    )
    from unittest.mock import patch

    with patch("app.auth.dependencies.get_settings", return_value=oidc), TestClient(app) as client:
        streamable = client.post(
            "/gateway/mcp",
            headers=_PROTOCOL_HEADERS,
            json={"jsonrpc": "2.0", "id": 1,
                  "method": "initialize", "params": {}},
        )
        sse = client.get("/gateway/sse")

    assert streamable.status_code == 401
    assert sse.status_code == 401
