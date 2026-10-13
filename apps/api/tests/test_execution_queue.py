from uuid import uuid4

from sqlmodel import Session

from app.database import create_db_and_tables, engine
from app.execution_queue import (
    ExecutionConflict,
    claim_execution,
    enqueue_execution,
    finish_execution,
    heartbeat_execution,
    request_execution_cancellation,
)
from app.models import ExecutionJob, Project, Task
import pytest


def _task() -> str:
    suffix = uuid4().hex
    task_id = f"TASK-QUEUE-{suffix}"
    with Session(engine) as session:
        project = Project(name=f"Queue {suffix}", repository_path=".")
        session.add(project)
        session.commit()
        session.refresh(project)
        session.add(Task(
            id=task_id,
            project_id=project.id,
            title="Queue test",
            description="Exercise durable execution ownership",
        ))
        session.commit()
    return task_id


def test_enqueue_claim_heartbeat_and_finish_are_fenced():
    create_db_and_tables()
    task_id = _task()
    queued = enqueue_execution(task_id)

    assert enqueue_execution(task_id).id == queued.id
    claimed = claim_execution("worker-one", lease_seconds=30)
    assert claimed is not None
    assert claimed.id == queued.id
    assert claimed.lease_token
    assert not heartbeat_execution(claimed.id, "wrong-token", 30)
    assert heartbeat_execution(claimed.id, claimed.lease_token, 30)
    assert not finish_execution(claimed.id, "wrong-token", "DONE")
    assert finish_execution(
        claimed.id,
        claimed.lease_token,
        "DONE",
        result={"content": "governed"},
    )
    with Session(engine) as session:
        assert session.get(ExecutionJob, claimed.id).result == {
            "content": "governed"
        }

    assert enqueue_execution(task_id).id != queued.id
    assert request_execution_cancellation(task_id) == 1


def test_cancellation_stops_a_claimed_job_at_heartbeat():
    create_db_and_tables()
    task_id = _task()
    queued = enqueue_execution(task_id)
    claimed = claim_execution("worker-two", lease_seconds=30)

    assert claimed is not None and claimed.id == queued.id and claimed.lease_token
    assert request_execution_cancellation(task_id) == 1
    assert not heartbeat_execution(claimed.id, claimed.lease_token, 30)


def test_task_allows_only_one_active_execution_operation():
    create_db_and_tables()
    task_id = _task()
    enqueue_execution(task_id, "run")

    with pytest.raises(ExecutionConflict, match="active run execution"):
        enqueue_execution(
            task_id,
            "tool",
            {"tool": "read_file", "arguments": {"path": "README.md"}},
        )

    assert request_execution_cancellation(task_id) == 1
