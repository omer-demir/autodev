from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import Event, Project, Sandbox, Task
from app.workflow import cleanup_sandbox


@pytest.fixture(autouse=True)
def initialize_database():
    create_db_and_tables()


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
