from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, or_, select

from .database import engine
from .models import ExecutionJob


ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}
TERMINAL_JOB_STATUSES = {"DONE", "FAILED", "CANCELLED"}


class ExecutionConflict(RuntimeError):
    pass


def enqueue_execution(
    task_id: str,
    operation: str = "run",
    payload: dict | None = None,
    *,
    deduplicate: bool = True,
) -> ExecutionJob:
    payload_value = payload or {}
    deduplication_key = f"{task_id}:active" if deduplicate else None
    with Session(engine) as session:
        if deduplicate:
            existing = session.exec(
                select(ExecutionJob).where(
                    ExecutionJob.task_id == task_id,
                    ExecutionJob.status.in_(ACTIVE_JOB_STATUSES),
                )
            ).first()
            if existing:
                if existing.operation == operation and existing.payload == payload_value:
                    return existing
                raise ExecutionConflict(
                    f"Task {task_id} already has an active {existing.operation} execution"
                )
        job = ExecutionJob(
            id=f"JOB-{uuid4().hex}",
            task_id=task_id,
            operation=operation,
            deduplication_key=deduplication_key,
            payload=payload_value,
        )
        session.add(job)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            concurrent = session.exec(
                select(ExecutionJob).where(
                    ExecutionJob.deduplication_key == deduplication_key
                )
            ).one()
            if concurrent.operation == operation and concurrent.payload == payload_value:
                return concurrent
            raise ExecutionConflict(
                f"Task {task_id} already has an active {concurrent.operation} execution"
            )
        session.refresh(job)
        return job


def claim_execution(
    worker_id: str,
    *,
    lease_seconds: int,
) -> ExecutionJob | None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        exhausted = session.exec(
            select(ExecutionJob).where(
                ExecutionJob.status == "RUNNING",
                ExecutionJob.leased_until < now,
                ExecutionJob.attempts >= ExecutionJob.max_attempts,
            )
        ).all()
        for item in exhausted:
            item.status = "FAILED"
            item.error = "Execution lease expired after maximum attempts"
            item.deduplication_key = None
            item.updated_at = now
            session.add(item)
        if exhausted:
            session.commit()
        statement = (
            select(ExecutionJob)
            .where(
                or_(
                    ExecutionJob.status == "QUEUED",
                    (
                        (ExecutionJob.status == "RUNNING")
                        & (ExecutionJob.leased_until < now)
                    ),
                ),
                ExecutionJob.cancel_requested.is_(False),
                ExecutionJob.attempts < ExecutionJob.max_attempts,
            )
            .order_by(ExecutionJob.created_at)
        )
        if engine.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = session.exec(statement).first()
        if not job:
            return None
        job.status = "RUNNING"
        job.worker_id = worker_id
        job.lease_token = uuid4().hex
        job.leased_until = now + timedelta(seconds=lease_seconds)
        job.attempts += 1
        job.error = None
        job.updated_at = now
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def heartbeat_execution(job_id: str, lease_token: str, lease_seconds: int) -> bool:
    with Session(engine) as session:
        job = session.get(ExecutionJob, job_id)
        if not job or job.status != "RUNNING" or job.lease_token != lease_token:
            return False
        now = datetime.now(UTC)
        job.leased_until = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        session.add(job)
        session.commit()
        return not job.cancel_requested


def finish_execution(
    job_id: str,
    lease_token: str,
    status: str,
    error: str | None = None,
    result: dict | None = None,
) -> bool:
    if status not in TERMINAL_JOB_STATUSES:
        raise ValueError(f"Unsupported terminal job status: {status}")
    with Session(engine) as session:
        job = session.get(ExecutionJob, job_id)
        if not job or job.lease_token != lease_token:
            return False
        job.status = status
        job.error = error
        job.result = result
        job.deduplication_key = None
        job.leased_until = None
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.commit()
        return True


def request_execution_cancellation(task_id: str) -> int:
    count = 0
    with Session(engine) as session:
        jobs = session.exec(
            select(ExecutionJob).where(
                ExecutionJob.task_id == task_id,
                ExecutionJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        ).all()
        for job in jobs:
            job.cancel_requested = True
            if job.status == "QUEUED":
                job.status = "CANCELLED"
                job.deduplication_key = None
            job.updated_at = datetime.now(UTC)
            session.add(job)
            count += 1
        session.commit()
    return count
