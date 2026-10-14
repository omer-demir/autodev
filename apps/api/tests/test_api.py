import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select
import yaml

from app.database import engine
from app.main import app
from app.models import (
    Approval,
    Event,
    ExecutionJob,
    Message,
    Project,
    Sandbox,
    Task,
    TaskArtifact,
    TaskStatus,
    WorkspaceRevision,
)
from app.repositories import RepositoryError


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_task_lists_are_bounded_filterable_sortable_and_paginated():
    suffix = uuid4().hex
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Listing {suffix}", repository_path="/tmp/listing")
            session.add(project)
            session.commit()
            session.refresh(project)
            for index in range(7):
                session.add(Task(
                    id=f"TASK-LIST-{suffix}-{index}",
                    project_id=project.id,
                    title=f"Listing {suffix} {index}",
                    description="Task list coverage",
                    status=TaskStatus.DONE if index % 2 else TaskStatus.DRAFT,
                    progress=index,
                ))
            session.commit()

        dashboard = client.get("/api/dashboard").json()
        page = client.get(
            "/api/tasks",
            params={
                "query": suffix,
                "status": "DONE",
                "sort_by": "progress",
                "sort_order": "desc",
                "page": 2,
                "page_size": 2,
            },
        )

    assert len(dashboard["tasks"]) <= 5
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 3
    assert payload["page"] == 2
    assert len(payload["items"]) == 1
    assert all(item["status"] == "DONE" for item in payload["items"])
    assert payload["counts"]["done"] >= 3


def test_task_changes_are_loaded_by_directory_and_file():
    suffix = uuid4().hex
    task_id = f"TASK-CHANGES-{suffix}"
    patch_text = """diff --git a/src/api/main.py b/src/api/main.py
index 1111111..2222222 100644
--- a/src/api/main.py
+++ b/src/api/main.py
@@ -1 +1 @@
-old
+new
diff --git a/README.md b/README.md
index 3333333..4444444 100644
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old readme
+new readme
"""
    files = [
        {"path": "README.md", "status": "modified", "additions": 1, "deletions": 1},
        {"path": "src/api/main.py", "status": "modified",
            "additions": 1, "deletions": 1},
        {"path": "src/api/routes/tasks.py", "status": "added",
            "additions": 20, "deletions": 0},
        {"path": "src/web/page.tsx", "status": "modified",
            "additions": 4, "deletions": 2},
        {"path": "node_modules/example/index.js",
            "status": "added", "additions": 50, "deletions": 0},
    ]
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Changes {suffix}", repository_path=f"/tmp/changes-{suffix}"
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            session.add(Task(
                id=task_id,
                project_id=project.id,
                title="Browse changed files",
                description="Load folders on demand",
            ))
            session.add(TaskArtifact(
                task_id=task_id,
                kind="changes",
                content={"files": files, "diff": patch_text,
                         "revision": "revision-1"},
            ))
            session.commit()

        detail = client.get(f"/api/tasks/{task_id}")
        root = client.get(f"/api/tasks/{task_id}/changes")
        source = client.get(
            f"/api/tasks/{task_id}/changes", params={"path": "src"}
        )
        api_directory = client.get(
            f"/api/tasks/{task_id}/changes", params={"path": "src/api"}
        )
        file_diff = client.get(
            f"/api/tasks/{task_id}/changes/diff",
            params={"path": "src/api/main.py"},
        )
        invalid = client.get(
            f"/api/tasks/{task_id}/changes", params={"path": "../secrets"}
        )

    assert detail.status_code == 200
    assert detail.json()["artifacts"]["changes"] == {
        "file_count": 5,
        "revision": "revision-1",
    }
    assert [item["name"] for item in root.json()["entries"]] == [
        "node_modules", "src", "README.md"
    ]
    assert root.json()["entries"][0]["file_count"] == 1
    assert [item["name"] for item in source.json()["entries"]] == [
        "api", "web"]
    assert [item["name"] for item in api_directory.json()["entries"]] == [
        "routes", "main.py"
    ]
    assert file_diff.status_code == 200
    assert file_diff.json()["diff"].startswith(
        "diff --git a/src/api/main.py b/src/api/main.py"
    )
    assert "README.md" not in file_diff.json()["diff"]
    assert invalid.status_code == 400


def test_repository_removal_deletes_attached_tasks_and_owned_data():
    suffix = uuid4().hex
    task_id = f"TASK-DELETE-{suffix}"
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Delete repository {suffix}",
                repository_path=f"/tmp/delete-{suffix}",
                source_type="empty",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = project.id
            session.add(Task(
                id=task_id,
                project_id=project_id,
                title="Delete attached task",
                description="Exercise project deletion",
                status=TaskStatus.DONE,
            ))
            session.add(Approval(
                id=f"APPROVAL-{suffix}", task_id=task_id, action="git.commit"
            ))
            session.add(Event(
                task_id=task_id, type="task.completed", title="Completed"
            ))
            session.add(ExecutionJob(
                id=f"JOB-{suffix}", task_id=task_id, status="DONE"
            ))
            session.add(Message(
                task_id=task_id, role="user", content="Delete this task"
            ))
            session.add(Sandbox(
                id=f"SANDBOX-{suffix}", task_id=task_id, status="KILLED"
            ))
            session.add(TaskArtifact(
                task_id=task_id, kind="changes", content={"files": []}
            ))
            session.add(WorkspaceRevision(
                id=f"REV-{suffix}",
                task_id=task_id,
                organization_id="local",
                digest=suffix,
                object_key=f"tasks/{task_id}/revision.tar.gz",
                size_bytes=1,
            ))
            session.commit()

        terminate = AsyncMock()
        with (
            patch("app.main.terminate_task", terminate),
            patch("app.main.evidence_provider.delete_task") as delete_evidence,
            patch("app.main.workspace_snapshots.delete_task") as delete_snapshots,
            patch("app.main.remove_task_workspace") as delete_workspace,
        ):
            response = client.delete(f"/api/projects/{project_id}")

        assert response.status_code == 204
        assert response.content == b""
        terminate.assert_awaited_once_with(task_id)
        delete_evidence.assert_called_once_with(task_id)
        delete_snapshots.assert_called_once_with(task_id)
        delete_workspace.assert_called_once_with(task_id)
        with Session(engine) as session:
            assert session.get(Project, project_id) is None
            assert session.get(Task, task_id) is None
            for model in (
                Approval,
                Event,
                ExecutionJob,
                Message,
                Sandbox,
                TaskArtifact,
                WorkspaceRevision,
            ):
                assert session.exec(
                    select(model).where(model.task_id == task_id)
                ).all() == []


def test_repository_removal_requires_attached_tasks_to_be_inactive():
    suffix = uuid4().hex
    task_id = f"TASK-ACTIVE-{suffix}"
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Active repository {suffix}",
                repository_path=f"/tmp/active-{suffix}",
                source_type="empty",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = project.id
            session.add(Task(
                id=task_id,
                project_id=project_id,
                title="Active attached task",
                description="Do not delete while running",
                status=TaskStatus.IMPLEMENTATION,
            ))
            session.commit()

        response = client.delete(f"/api/projects/{project_id}")

        assert response.status_code == 409
        assert task_id in response.json()["detail"]
        with Session(engine) as session:
            assert session.get(Project, project_id) is not None
            assert session.get(Task, task_id) is not None


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
        assert task["workflow_id"] == "sdlc"
        assert task["agent_id"] == "did:local:developer"
        with Session(engine) as session:
            workflow_snapshot = session.exec(
                select(TaskArtifact).where(
                    TaskArtifact.task_id == task["id"],
                    TaskArtifact.kind == "workflow-definition",
                )
            ).one()
            assert workflow_snapshot.content["workflow_id"] == "sdlc"
            assert workflow_snapshot.content["definition"]["name"] == "Governed SDLC"
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
        cancelled = client.post(f"/api/tasks/{task['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        with Session(engine) as session:
            stored = session.get(Task, task["id"])
            assert stored is not None
            assert stored.status == TaskStatus.CANCELLED
            stored.status = TaskStatus.DRAFT
            stored.phase = "Intake"
            session.add(stored)
            session.commit()
        with patch("app.main.schedule_task") as schedule:
            assert client.post(
                f"/api/tasks/{task['id']}/run").status_code == 202
            schedule.assert_called_once_with(task["id"])


def test_task_creation_accepts_explicit_evaluation_bypass():
    suffix = uuid4().hex
    agent_id = f"trial-{suffix}"

    def definition(kind: str, identifier: str) -> dict:
        if kind == "workflows":
            return {
                "data": {
                    "name": "Trial workflow",
                    "version": "1.0.0",
                    "status": "active",
                    "stages": [],
                }
            }
        assert kind == "agents"
        assert identifier == agent_id
        return {
            "data": {
                "name": "Trial agent",
                "version": "1.0.0",
                "status": "draft",
                "evaluation_required": False,
                "identity": {"id": f"did:local:{agent_id}"},
                "capabilities": ["repository.read"],
            }
        }

    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Bypass trial {suffix}",
                repository_path=f"/tmp/bypass-{suffix}",
                source_type="empty",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = project.id
        with patch("app.main.get_definition", side_effect=definition):
            response = client.post("/api/tasks", json={
                "project_id": project_id,
                "title": "Try imported agent",
                "description": "Run before an evaluation dataset exists",
                "workflow_id": "trial",
                "agent_id": f"did:local:{agent_id}",
                "mode": "assessment",
            })

    assert response.status_code == 201
    assert response.json()["agent_id"] == f"did:local:{agent_id}"


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

        capabilities = client.get("/api/runtime-capabilities")
        assert capabilities.status_code == 200
        assert "repository.read" in capabilities.json()["capabilities"]
        assert capabilities.json()["resolvers"] == ["command-v1"]

        datasets = client.get("/api/evaluation-datasets").json()
        dataset = next(
            item for item in datasets if item["agent_id"] == "developer")
        response = client.post(
            "/api/evaluations/declaration",
            json={"agent_id": "developer", "dataset_id": dataset["id"]},
        )
        assert response.status_code == 201
        result = response.json()
        assert result["overall_score"] == 1.0
        assert result["scores"]["safety"] == 1.0
        assert result["provenance"] == {
            "execution": "static", "agent_executed": False,
            "dataset_hash": dataset["content_hash"],
        }


def test_workflow_stage_assignment_revalidates_saved_definition():
    workflow = {
        "kind": "workflows",
        "id": "delivery",
        "raw": "",
        "data": {
            "name": "Delivery",
            "version": "1.0.0",
            "phases": [],
            "stages": [{"id": "review", "agent": "did:local:reviewer"}],
        },
    }
    saved = {**workflow, "data": {**workflow["data"]}}
    with patch(
        "app.routers.registry.get_definition",
        side_effect=[{"id": "security"}, workflow],
    ), patch(
        "app.routers.registry.save_definition", return_value=saved
    ) as save, TestClient(app) as client:
        response = client.patch(
            "/api/registry/workflows/delivery/stages/review",
            json={"agent_id": "security"},
        )

    assert response.status_code == 200
    kind, identifier, raw = save.call_args.args
    assert (kind, identifier) == ("workflows", "delivery")
    assert yaml.safe_load(raw)["stages"][0]["agent"] == "did:local:security"


def test_integration_import_endpoint_uses_governed_importer():
    imported = {
        "kind": "skills",
        "id": "review",
        "raw": "name: review",
        "data": {"name": "review"},
    }
    with patch(
        "app.routers.registry.import_external_definition",
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

        with (
            patch("app.main.complete_publication", complete),
            patch("app.main.validate_publication"),
        ):
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
    complete.assert_awaited_once_with(
        task_id, "feature/governed", True, "local-admin"
    )


def test_pull_request_publication_requires_authentication_before_approval(tmp_path):
    suffix = uuid4().hex
    task_id = f"TASK-PUBLISH-AUTH-{suffix}"
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Publish auth {suffix}",
                source_type="github",
                repository_path="",
                repository_url="https://github.com/acme/repo",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            session.add(Task(
                id=task_id,
                project_id=project.id,
                title="Publish governed change",
                description="Verify authentication preflight",
                status=TaskStatus.DONE,
            ))
            session.commit()

        with patch(
            "app.main.validate_publication",
            side_effect=RepositoryError(
                "Disable pull request creation to push with SSH"),
        ):
            response = client.post(
                f"/api/tasks/{task_id}/publish",
                json={"branch": "feature/ssh", "create_pull_request": True},
            )

    assert response.status_code == 409
    assert "push with SSH" in response.json()["detail"]


def test_publication_failure_keeps_approval_pending(tmp_path):
    suffix = uuid4().hex
    task_id = f"TASK-PUBLISH-FAIL-{suffix}"
    approval_id = f"APR-PUBLISH-FAIL-{suffix}"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with TestClient(app) as client:
        with Session(engine) as session:
            project = Project(
                name=f"Publish failure {suffix}", repository_path=str(workspace)
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            session.add(Task(
                id=task_id,
                project_id=project.id,
                title="Publish governed change",
                description="Verify retryable approval",
                status=TaskStatus.DONE,
            ))
            session.add(Approval(
                id=approval_id,
                task_id=task_id,
                action="repository.publish",
                scope={"branch": "feature/retry",
                       "create_pull_request": False},
            ))
            session.commit()

        with patch(
            "app.main.complete_publication",
            AsyncMock(side_effect=RepositoryError("SSH push failed")),
        ):
            response = client.post(f"/api/approvals/{approval_id}/approve")

        with Session(engine) as session:
            approval = session.get(Approval, approval_id)
            assert approval is not None
            assert approval.status == "PENDING"
            assert approval.approver_id is None

    assert response.status_code == 502
    assert response.json()["detail"] == "SSH push failed"


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
