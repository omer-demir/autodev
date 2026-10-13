import asyncio
import logging
import os
import signal
import socket
from time import monotonic
from contextlib import suppress

from opentelemetry.trace import Status, StatusCode
from sqlmodel import Session

from .config import get_settings
from .database import create_db_and_tables, engine
from .execution_queue import claim_execution, finish_execution, heartbeat_execution
from .models import Task, TaskStatus
from .observability import (
    configure_logging,
    configure_observability,
    mark_error,
    observe_worker_job,
    shutdown_observability,
    tracer,
)
from .remote_tools import run_governed_tool
from .workflow import run_task


logger = logging.getLogger("autodev.worker")
_SUCCESSFUL_TASK_STATUSES = {
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
    TaskStatus.AWAITING_APPROVAL,
}


async def execute_job(job) -> None:
    started = monotonic()
    final_status = "FAILED"
    settings = get_settings()
    with tracer().start_as_current_span(
        "autodev.worker.job",
        attributes={
            "autodev.job.id": job.id,
            "autodev.task_id": job.task_id,
            "autodev.operation": job.operation,
        },
    ) as span:
        if not job.lease_token:
            raise RuntimeError(f"Execution job {job.id} has no lease token")
        if job.operation == "run":
            operation = run_task(job.task_id)
        elif job.operation == "tool":
            operation = run_governed_tool(
                job.id,
                job.task_id,
                str(job.payload.get("tool") or ""),
                dict(job.payload.get("arguments") or {}),
            )
        else:
            finish_execution(
                job.id,
                job.lease_token,
                "FAILED",
                f"Unsupported execution operation: {job.operation}",
            )
            span.set_status(Status(StatusCode.ERROR, "unsupported operation"))
            return

        execution = asyncio.create_task(operation)
        try:
            while True:
                done, _ = await asyncio.wait(
                    {execution}, timeout=settings.worker_heartbeat_seconds
                )
                if done:
                    break
                active = heartbeat_execution(
                    job.id, job.lease_token, settings.worker_lease_seconds
                )
                if active:
                    span.add_event("worker.heartbeat")
                    continue
                execution.cancel()
                with suppress(asyncio.CancelledError):
                    await execution
                finish_execution(job.id, job.lease_token, "CANCELLED")
                final_status = "CANCELLED"
                return
            operation_result = await execution
            if job.operation == "run":
                with Session(engine) as session:
                    task = session.get(Task, job.task_id)
                    status = task.status if task else TaskStatus.FAILED
                status = "DONE" if status in _SUCCESSFUL_TASK_STATUSES else "FAILED"
                result = None
            else:
                status = "DONE"
                result = operation_result
            finish_execution(job.id, job.lease_token, status, result=result)
            final_status = status
            span.set_status(Status(StatusCode.OK if status ==
                            "DONE" else StatusCode.ERROR))
        except asyncio.CancelledError:
            final_status = "CANCELLED"
            execution.cancel()
            with suppress(asyncio.CancelledError):
                await execution
            raise
        except Exception as exc:
            mark_error(span, exc)
            logger.exception("Execution job %s failed", job.id)
            finish_execution(job.id, job.lease_token, "FAILED", str(exc))
        finally:
            observe_worker_job(
                operation=job.operation,
                status=final_status,
                duration_ms=max(0, int((monotonic() - started) * 1_000)),
            )


async def run_worker() -> None:
    settings = get_settings()
    if settings.execution_dispatch != "durable":
        raise RuntimeError(
            "Worker requires WORKBENCH_EXECUTION_DISPATCH=durable")
    create_db_and_tables()
    worker_id = os.getenv(
        "WORKBENCH_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for value in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(value, stop.set)

    logger.info("Autodev worker %s started", worker_id)
    while not stop.is_set():
        job = claim_execution(
            worker_id, lease_seconds=settings.worker_lease_seconds)
        if job:
            await execute_job(job)
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
        except TimeoutError:
            pass


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    configure_logging()
    configure_observability()
    try:
        asyncio.run(run_worker())
    finally:
        shutdown_observability()


if __name__ == "__main__":
    main()
