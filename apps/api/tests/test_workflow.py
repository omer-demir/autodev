from copy import deepcopy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import Event, Project, Sandbox, Task, TaskArtifact
from app.workflow import (
    _commit_subject,
    _collect_changes,
    _pull_request_body,
    _run_executable_workflow,
    _save_artifact,
    cleanup_sandbox,
)


@pytest.fixture(autouse=True)
def initialize_database():
    create_db_and_tables()


@pytest.mark.asyncio
async def test_pull_request_body_uses_model_output_without_request_or_file_sections():
    task = Task(
        id="TASK-PR-BODY",
        project_id=1,
        title="Improve publication",
        description="Do not copy this chat message into the pull request.",
        workflow_id="implementation",
        agent_id="did:local:developer",
        created_by="requester@example.com",
    )

    with patch(
        "app.workflow.generate_text",
        new=AsyncMock(return_value=(
            "## Summary\nImplement concise pull request metadata.\n\n"
            "## Changed files\nThis section is removed.\n\n"
            "## Message\nThis section is removed too.\n\n"
            "## Validation\nFour tests passed."
        )),
    ) as generate:
        body = await _pull_request_body(
            task,
            {
                "changes": {
                    "files": [{
                        "path": "src/publish.py",
                        "status": "modified",
                        "additions": 12,
                        "deletions": 3,
                    }],
                    "diff": "diff --git a/src/publish.py b/src/publish.py",
                },
                "tests": {"passed": 4, "failed": 0, "skipped": 0},
                "security": {"high": 0, "medium": 0, "low": 1},
            },
        )

    assert body == (
        "## Summary\nImplement concise pull request metadata.\n\n"
        "## Validation\nFour tests passed."
    )
    prompt = generate.await_args.kwargs["prompt"]
    assert task.description not in prompt
    assert "src/publish.py" in prompt
    assert "## Changed files" not in body
    assert "## Message" not in body


def test_collect_changes_records_individual_file_patches(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(workspace), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "--quiet")
    git("config", "user.name", "AutoDev Test")
    git("config", "user.email", "test@example.com")
    first = workspace / "first.txt"
    second = workspace / "second.txt"
    first.write_text("before\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")
    git("add", "first.txt", "second.txt")
    git("commit", "--quiet", "-m", "initial")
    first.write_text("after\n", encoding="utf-8")
    new_file = workspace / "new.txt"
    new_file.write_text("new content\n", encoding="utf-8")

    changes = _collect_changes(workspace)
    patches = {item["path"]: item["patch"] for item in changes["files"]}

    assert set(patches) == {"first.txt", "new.txt"}
    assert "after" in patches["first.txt"]
    assert "new content" in patches["new.txt"]
    assert "second.txt" not in patches["first.txt"]
    assert changes["files"][0]["additions"] == 1


@pytest.mark.asyncio
async def test_commit_subject_is_generated_from_diff_not_task_text():
    task = Task(
        id="TASK-COMMIT-SUBJECT",
        project_id=1,
        title="Please make these changes in the repository",
        description="This is a long conversational task request.",
    )
    with patch(
        "app.workflow.generate_text",
        new=AsyncMock(return_value="fix: summarize the actual change\nExtra text"),
    ) as generate:
        subject = await _commit_subject(task, "diff --git a/src/a.py b/src/a.py")

    assert subject == "fix: summarize the actual change"
    prompt = generate.await_args.kwargs["prompt"]
    assert task.title not in prompt
    assert task.description not in prompt
    assert "diff --git a/src/a.py b/src/a.py" in json.loads(prompt)["diff"]


@pytest.mark.asyncio
async def test_save_artifact_publishes_realtime_update():
    suffix = uuid4().hex
    task_id = f"TASK-ARTIFACT-{suffix}"
    with Session(engine) as session:
        project = Project(
            name=f"Artifact {suffix}",
            repository_path=f"/tmp/artifact-{suffix}",
            source_type="empty",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        session.add(Task(
            id=task_id,
            project_id=project.id,
            title="Live artifacts",
            description="Publish artifact updates",
            organization_id="local",
        ))
        session.commit()

        with (
            patch("app.workflow.evidence_provider.write"),
            patch(
                "app.workflow.event_hub.publish", new=AsyncMock()
            ) as publish,
        ):
            await _save_artifact(
                session,
                task_id,
                "plan",
                {"requirements": [], "steps": [], "acceptance": []},
            )

        artifact = session.exec(select(TaskArtifact).where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.kind == "plan",
        )).one()
        assert artifact.content["steps"] == []
        publish.assert_awaited_once_with({
            "event": "artifact.updated",
            "task_id": task_id,
            "organization_id": "local",
            "kind": "plan",
        })


@pytest.mark.asyncio
async def test_cleanup_sandbox_removes_container_but_preserves_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    marker = workspace / "committed-change.txt"
    marker.write_text("preserved", encoding="utf-8")
    suffix = uuid4().hex
    sandbox = Sandbox(
        id=f"SBX-CLEANUP-SUCCESS-{suffix}",
        task_id=f"TASK-CLEANUP-SUCCESS-{suffix}",
        container_id="container-success",
        host_workspace=str(workspace),
    )
    with Session(engine) as session:
        project = Project(
            name=f"cleanup-{suffix}", repository_path=str(workspace))
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        session.add(Task(
            id=sandbox.task_id, project_id=project.id,
            title="Cleanup test", description="Verify sandbox cleanup",
        ))
        session.add(sandbox)
        session.commit()
        with patch("app.workflow.sandbox_provider.kill", new=AsyncMock()) as kill:
            assert await cleanup_sandbox(session, sandbox.task_id, "test completion")
            assert await cleanup_sandbox(session, sandbox.task_id, "duplicate cleanup")

        kill.assert_awaited_once_with("container-success")
        session.refresh(sandbox)
        assert sandbox.status == "KILLED"
        assert marker.read_text(encoding="utf-8") == "preserved"
        events = session.exec(
            select(Event).where(
                Event.task_id == sandbox.task_id,
                Event.type == "sandbox.killed",
            )
        ).all()
        assert len(events) == 1


@pytest.mark.asyncio
async def test_cleanup_failure_is_recorded_without_changing_status():
    suffix = uuid4().hex
    sandbox = Sandbox(
        id=f"SBX-CLEANUP-FAILURE-{suffix}",
        task_id=f"TASK-CLEANUP-FAILURE-{suffix}",
        container_id="container-failure",
    )
    with Session(engine) as session:
        project = Project(
            name=f"cleanup-{suffix}", repository_path="/tmp/cleanup")
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        session.add(Task(
            id=sandbox.task_id, project_id=project.id,
            title="Cleanup failure test", description="Verify cleanup failure evidence",
        ))
        session.add(sandbox)
        session.commit()
        with patch(
            "app.workflow.sandbox_provider.kill",
            new=AsyncMock(side_effect=RuntimeError("daemon unavailable")),
        ):
            assert not await cleanup_sandbox(session, sandbox.task_id, "failed task")

        session.refresh(sandbox)
        assert sandbox.status == "READY"
        event = session.exec(
            select(Event).where(
                Event.task_id == sandbox.task_id,
                Event.type == "sandbox.cleanup_failed",
            )
        ).one()
        assert "daemon unavailable" in event.detail


@pytest.mark.asyncio
async def test_executable_workflow_hands_off_artifacts_and_uses_stage_sandbox():
    task = SimpleNamespace(
        id="TASK-STAGES",
        workflow_id="delivery",
        organization_id="local",
        agent_id="did:local:researcher",
        title="Deliver feature",
        description="Research and implement the feature",
        mode="change",
        verbose_logging=False,
    )
    workflow = {
        "version": "1.0.0",
        "orchestration": {"mode": "sequential", "max_parallel": 1},
        "stages": [
            {
                "id": "research",
                "agent": "did:local:researcher",
                "responsibility": "Research.",
                "inputs": ["request", "workspace"],
                "outputs": ["research-output"],
            },
            {
                "id": "implement",
                "agent": "did:local:implementer",
                "responsibility": "Implement.",
                "inputs": ["request", "research-output", "workspace"],
                "outputs": ["implementation-output"],
            },
        ],
    }
    definitions = {
        "researcher": {
            "capabilities": ["repository.read"],
            "environment": {"workspace_access": "read-only", "network_mode": "none"},
        },
        "implementer": {
            "capabilities": ["repository.read", "repository.write"],
            "environment": {
                "image": "implementation:local",
                "workspace_access": "read-write",
                "network_mode": "bridge",
                "pool_profile": "implementation-pool",
            },
        },
    }
    saved_artifacts: dict[str, dict] = {}
    workflow_run_history: list[dict] = []
    runtime_calls: list[dict] = []

    async def run_agent(_runtime, **kwargs):
        runtime_calls.append(kwargs)
        return f"completed {kwargs['stage_context']['stage_id']}"

    async def save_artifact(_session, _task_id, kind, content):
        saved_artifacts[kind] = deepcopy(content)
        if kind == "workflow-run":
            workflow_run_history.append(deepcopy(content))

    with (
        patch("app.workflow.get_definition", side_effect=lambda kind, identifier: {
            "data": definitions[identifier]
        }),
        patch(
            "app.workflow.agent_identity_service.verify",
            return_value=SimpleNamespace(did="did:verified:agent"),
        ),
        patch("app.workflow.AgentRuntime.run", new=run_agent),
        patch("app.workflow.record_event", new=AsyncMock()),
        patch("app.workflow._save_artifact", new=save_artifact),
        patch("app.workflow._collect_changes", return_value={
            "files": [], "diff": "", "status": "",
        }),
        patch(
            "app.workflow.sandbox_provider.create",
            new=AsyncMock(
                return_value={"container_id": "implementation-container"}),
        ) as create,
        patch("app.workflow.sandbox_provider.kill", new=AsyncMock()) as kill,
    ):
        summary = await _run_executable_workflow(
            session=MagicMock(),
            task=task,
            workflow=workflow,
            workspace=Path("/tmp/workspace"),
            container_id="research-container",
            model_name="auto",
            callback=AsyncMock(),
            steering=[],
            session_context=[],
            steering_provider=AsyncMock(return_value=[]),
            model_recovery=AsyncMock(),
        )

    assert summary == "completed implement"
    assert runtime_calls[0]["container_id"] == "research-container"
    assert runtime_calls[1]["container_id"] == "implementation-container"
    assert runtime_calls[1]["stage_context"]["input_artifacts"] == {
        "research-output": saved_artifacts["research-output"]
    }
    create.assert_awaited_once()
    assert create.await_args.args[0]["workspace_access"] == "read-write"
    assert create.await_args.args[0]["network_mode"] == "bridge"
    kill.assert_awaited_once_with("implementation-container")
    assert saved_artifacts["workflow-run"]["status"] == "completed"
    assert any(
        state["stages"].get("research", {}).get("status") == "running"
        and state["stages"]["research"]["agent_id"] == "did:local:researcher"
        and state["stages"]["research"]["responsibility"] == "Research."
        for state in workflow_run_history
    )
    assert saved_artifacts["workflow-run"]["stages"]["implement"]["status"] == (
        "completed"
    )
