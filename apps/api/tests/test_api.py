import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.database import engine
from app.main import app
from app.models import Event, Message, Project, Sandbox, Task, TaskArtifact, TaskStatus


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_task_can_be_created_and_started(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", str(repository)],
                   check=True, capture_output=True)
    (repository / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "-c", "user.name=Test", "-c",
         "user.email=test@example.com", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects",
            json={"name": "Test repository", "repository_path": str(
                repository), "source_type": "local"},
        )
        assert project_response.status_code == 201
        project = project_response.json()
        response = client.post(
            "/api/tasks",
            json={
                "project_id": project["id"],
                "title": "Exercise task creation",
                "description": "Verify the task API and workflow entry point",
            },
        )
        assert response.status_code == 201
        task = response.json()
        assert task["status"] == "DRAFT"
        assert task["mode"] == "change"
        marketplace = client.get("/api/marketplace/agents")
        assert marketplace.status_code == 200
        developer = next(
            item for item in marketplace.json() if item["agent_id"] == "developer"
        )
        assert developer["agent_did"].startswith("did:mesh:")
        assert developer["verified"] is True
        steering = client.post(
            f"/api/tasks/{task['id']}/messages", json={"content": "Change direction"}
        )
        assert steering.status_code == 409
        assert "coding agent is active" in steering.json()["detail"]
        with Session(engine) as session:
            stored = session.get(Task, task["id"])
            stored.status = TaskStatus.IMPLEMENTATION
            session.add(stored)
            session.commit()
        accepted = client.post(
            f"/api/tasks/{task['id']}/messages", json={"content": "Use focused tests"}
        )
        assert accepted.status_code == 201
        assert accepted.json()["content"] == "Use focused tests"
        with Session(engine) as session:
            stored = session.get(Task, task["id"])
            stored.status = TaskStatus.DRAFT
            session.add(stored)
            session.commit()
        mode_response = client.patch(
            f"/api/tasks/{task['id']}/mode", json={"mode": "assessment"}
        )
        assert mode_response.status_code == 200
        assert mode_response.json()["mode"] == "assessment"
        with patch("app.main.schedule_task") as schedule:
            assert client.post(
                f"/api/tasks/{task['id']}/run").status_code == 202
            schedule.assert_called_once_with(task["id"])


def test_management_registry_and_evaluation():
    with TestClient(app) as client:
        agents = client.get("/api/registry/agents")
        assert agents.status_code == 200
        assert "developer" in {item["id"] for item in agents.json()}

        suites = client.get("/api/registry/evaluation-suites")
        assert suites.status_code == 200
        assert "baseline" in {item["id"] for item in suites.json()}

        policies = client.get("/api/registry/policies")
        assert policies.status_code == 200
        assert "development" in {item["id"] for item in policies.json()}

        response = client.post(
            "/api/evaluations/declaration",
            json={"agent_id": "developer", "suite_id": "baseline"},
        )
        assert response.status_code == 201
        result = response.json()
        assert result["overall_score"] == 1.0
        assert result["scores"]["safety"] == 1.0
        assert result["provenance"] == {
            "execution": "static", "agent_executed": False
        }


def test_integration_import_endpoint_uses_governed_importer():
    imported = {
        "kind": "skills",
        "id": "review",
        "raw": "name: review",
        "data": {"name": "review"},
    }
    with patch(
        "app.main.import_external_definition",
        new=AsyncMock(return_value=imported),
    ) as importer, TestClient(app) as client:
        response = client.post(
            "/api/integrations/import",
            json={
                "url": "https://github.com/example/skills/blob/main/review/SKILL.md",
                "kind": "skill",
                "identifier": "review",
            },
        )

    assert response.status_code == 201
    assert response.json() == imported
    importer.assert_awaited_once_with(
        "https://github.com/example/skills/blob/main/review/SKILL.md",
        kind="skill",
        identifier="review",
    )


def test_operational_overviews_are_available():
    with TestClient(app) as client:
        sandboxes = client.get("/api/sandboxes")
        security = client.get("/api/security")
        governance = client.get("/api/governance")
        evidence = client.get("/api/evidence")

    assert sandboxes.status_code == 200
    assert isinstance(sandboxes.json(), list)
    assert security.status_code == 200
    assert set(security.json()) == {"summary", "findings"}
    assert governance.status_code == 200
    assert set(governance.json()) == {"summary", "approvals", "decisions"}
    assert evidence.status_code == 200
    assert isinstance(evidence.json(), list)


def test_publication_waits_for_explicit_scoped_approval(tmp_path):
    suffix = uuid4().hex
    task_id = f"TASK-PUBLISH-{suffix}"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    complete = AsyncMock()
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Publish {suffix}", repository_path=str(workspace))
            session.add(project)
            session.commit()
            session.refresh(project)
            task = Task(
                id=task_id,
                project_id=project.id,
                title="Publish governed change",
                description="Verify the approval boundary",
                status=TaskStatus.DONE,
            )
            session.add(task)
            session.add(Sandbox(
                id=f"SBX-PUBLISH-{suffix}",
                task_id=task_id,
                host_workspace=str(workspace),
            ))
            session.commit()

        with patch("app.main.complete_publication", complete):
            response = client.post(
                f"/api/tasks/{task_id}/publish",
                json={"branch": "feature/governed",
                      "create_pull_request": True},
            )
            assert response.status_code == 202
            payload = response.json()
            assert payload["actions"] == ["git.push", "pull_request.create"]
            complete.assert_not_awaited()

            approval = client.post(
                f"/api/approvals/{payload['approval_id']}/approve"
            )

    assert approval.status_code == 200
    assert approval.json()["scope"] == {
        "branch": "feature/governed",
        "create_pull_request": True,
        "actions": ["git.push", "pull_request.create"],
    }
    complete.assert_awaited_once_with(task_id, "feature/governed", True)


def test_agent_telemetry_aggregates_run_observability():
    started = datetime.now(UTC) - timedelta(seconds=12)
    with Session(engine) as session:
        project = Project(name="Telemetry", repository_path="/tmp/telemetry")
        session.add(project)
        session.commit()
        session.refresh(project)
        task = Task(
            id="TASK-TELEMETRY", project_id=project.id, title="Observe agent run",
            description="Collect operational telemetry", status=TaskStatus.DONE,
            phase="Done", agent_id="did:local:developer", created_at=started,
            updated_at=started + timedelta(seconds=12),
        )
        session.add(task)
        events = [
            Event(task_id=task.id, type="task.created",
                  title="Task created", created_at=started),
            Event(task_id=task.id, type="agent.started", title="Agent started",
                  created_at=started + timedelta(seconds=1)),
            Event(task_id=task.id, type="model.call", title="Model invocation",
                  created_at=started + timedelta(seconds=2)),
            Event(
                task_id=task.id, type="model.completed", title="Model completed",
                data={"provider": "ollama", "model": "local-test", "usage": {
                    "input_tokens": 120, "output_tokens": 30,
                }, "latency_ms": 750}, created_at=started + timedelta(seconds=3),
            ),
            Event(task_id=task.id, type="tool.requested",
                  title="read_file", created_at=started + timedelta(seconds=4)),
            Event(
                task_id=task.id, type="tool.allowed", title="repository.read allow",
                detail="Allowed by development policy", data={
                    "capability": "repository.read", "decision": "allow",
                    "policy": "development-v1",
                }, created_at=started + timedelta(seconds=4, milliseconds=50),
            ),
            Event(
                task_id=task.id, type="tool.completed", title="read_file",
                data={"capability": "repository.read", "latency_ms": 125},
                created_at=started + timedelta(seconds=4, milliseconds=125),
            ),
            Event(
                task_id=task.id, type="tool.denied", title="production.deploy deny",
                detail="Capability denied", severity="error", data={
                    "capability": "production.deploy", "decision": "deny",
                    "policy": "development-v1",
                }, created_at=started + timedelta(seconds=5),
            ),
            Event(task_id=task.id, type="task.completed", title="Task completed",
                  created_at=started + timedelta(seconds=12)),
        ]
        session.add_all(events)
        session.add(Message(
            task_id=task.id, role="assistant", content="Implemented telemetry.",
            created_at=started + timedelta(seconds=6),
        ))
        session.add(TaskArtifact(
            task_id=task.id, kind="security", content={
                "high": 0, "medium": 1, "low": 0,
                "scanners": {"Semgrep": "findings"},
            },
        ))
        session.commit()

    with TestClient(app) as client:
        response = client.get("/api/agents/developer/telemetry")
        task_response = client.get("/api/tasks/TASK-TELEMETRY/observability")

    assert response.status_code == 200
    telemetry = response.json()
    run = next(item for item in telemetry["runs"]
               if item["task_id"] == "TASK-TELEMETRY")
    assert run["totals"] == {
        "input_tokens": 120, "output_tokens": 30, "tokenized_calls": 1,
        "model_calls": 1, "tool_calls": 1, "estimated_cost_usd": 0.0,
        "priced_calls": 1, "unpriced_calls": 0,
    }
    assert run["model_calls"][0]["latency_ms"] == 750
    assert run["tools"][0]["latency_ms"] == 125
    assert run["safety"]["denied_actions"] == 1
    assert run["safety"]["security"]["medium"] == 1
    assert run["messages"][0]["content"] == "Implemented telemetry."
    assert run["phase_timings"]
    assert task_response.status_code == 200
    assert task_response.json()["task_id"] == "TASK-TELEMETRY"
    assert task_response.json()["totals"] == run["totals"]
