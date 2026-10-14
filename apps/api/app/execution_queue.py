from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlmodel import Session, or_, select

from .database import engine
from .models import ExecutionJob
from .observability import observe_execution_queue


ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}
TERMINAL_JOB_STATUSES = {"DONE", "FAILED", "CANCELLED"}


class ExecutionConflict(RuntimeError):
    pass


def _observe_queue_state(
    session: Session, *, transition: str | None = None,
    transition_count: int = 1,
) -> None:
    counts = {
        status: int(session.exec(
            select(func.count(ExecutionJob.id)).where(
                ExecutionJob.status == status
            )
        ).one())
        for status in ("QUEUED", "RUNNING")
    }
    observe_execution_queue(
        queued=counts["QUEUED"],
        running=counts["RUNNING"],
        transition=transition,
        transition_count=transition_count,
    )


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
                _observe_queue_state(session)
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
        _observe_queue_state(session, transition="QUEUED")
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
            _observe_queue_state(
                session,
                transition="FAILED",
                transition_count=len(exhausted),
            )
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
            _observe_queue_state(session)
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
        _observe_queue_state(session, transition="RUNNING")
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
        _observe_queue_state(session, transition=status)
        return True


def request_execution_cancellation(task_id: str) -> int:
    count = 0
    cancelled_count = 0
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
                cancelled_count += 1
            job.updated_at = datetime.now(UTC)
            session.add(job)
            count += 1
        session.commit()
        _observe_queue_state(
            session,
            transition="CANCELLED" if cancelled_count else None,
            transition_count=cancelled_count,
        )
    return count
