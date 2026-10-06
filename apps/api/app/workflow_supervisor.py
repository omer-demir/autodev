"""Hypervisor adapter for declarative workflow phase execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hypervisor import Hypervisor, SessionConfig

from .models import TaskStatus
from .registry import get_definition


@dataclass(frozen=True)
class PhaseTransition:
    phase_id: str
    label: str
    progress: int
    session_id: str
    saga_id: str


@dataclass
class _TaskWorkflow:
    session_id: str
    saga_id: str
    phases: dict[TaskStatus, dict[str, Any]]
    steps: dict[TaskStatus, str]
    completed: set[TaskStatus]


class WorkflowSupervisor:
    def __init__(self, hypervisor: Hypervisor | None = None) -> None:
        self.hypervisor = hypervisor or Hypervisor()
        self._tasks: dict[str, _TaskWorkflow] = {}

    async def transition(
        self,
        task_id: str,
        agent_id: str,
        status: TaskStatus,
        current_progress: int,
    ) -> PhaseTransition:
        workflow = self._tasks.get(task_id)
        if workflow is None:
            workflow = await self._start(task_id, agent_id)
        try:
            phase = workflow.phases[status]
        except KeyError as exc:
            raise RuntimeError(
                f"Workflow sdlc has no phase for status {status}") from exc

        if status not in workflow.completed:
            managed = self.hypervisor.get_session(workflow.session_id)
            if managed is None:
                raise RuntimeError(
                    f"Hypervisor session unavailable for task {task_id}")

            async def execute() -> dict[str, str]:
                return {"task_id": task_id, "phase": phase["id"], "status": status.value}

            await managed.saga.execute_step(
                workflow.saga_id, workflow.steps[status], execute
            )
            workflow.completed.add(status)

        progress = phase["progress"]
        transition = PhaseTransition(
            phase_id=phase["id"],
            label=phase["label"],
            progress=current_progress if progress == "inherit" else progress,
            session_id=workflow.session_id,
            saga_id=workflow.saga_id,
        )
        if status in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            await self.hypervisor.terminate_session(workflow.session_id)
            self._tasks.pop(task_id, None)
        return transition

    async def _start(self, task_id: str, agent_id: str) -> _TaskWorkflow:
        definition = get_definition("workflows", "sdlc")["data"]
        phases = {
            TaskStatus(phase["status"]): phase for phase in definition["phases"]
        }
        managed = await self.hypervisor.create_session(
            SessionConfig(max_participants=1, enable_audit=True),
            creator_did=agent_id,
        )
        session_id = managed.sso.session_id
        await self.hypervisor.join_session(session_id, agent_id, sigma_raw=0.5)
        await self.hypervisor.activate_session(session_id)
        saga = managed.saga.create_saga(session_id)
        steps = {
            status: managed.saga.add_step(
                saga.saga_id,
                action_id=f"workflow.{phase['id']}",
                agent_did=agent_id,
                execute_api=f"workflow://{task_id}/{phase['id']}",
            ).step_id
            for status, phase in phases.items()
        }
        workflow = _TaskWorkflow(
            session_id, saga.saga_id, phases, steps, set())
        self._tasks[task_id] = workflow
        return workflow


workflow_supervisor = WorkflowSupervisor()
