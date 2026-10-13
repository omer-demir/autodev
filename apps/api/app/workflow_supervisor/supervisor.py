from dataclasses import asdict

from ..config import get_settings
from ..models import TaskStatus
from ..registry import get_definition
from ..runtime_supervision import (
    ActionDecision,
    ActionSpec,
    ElevationGrant,
    ExecutionTier,
    RuntimeSupervisorProvider,
    SupervisionConfigurationError,
    SupervisionDeniedError,
    TerminationResult,
    get_runtime_supervisor_provider,
)
from .phase_transition import PhaseTransition
from .task_workflow import TaskWorkflow


class WorkflowSupervisor:
    def __init__(self, provider: RuntimeSupervisorProvider | None = None) -> None:
        self.provider = provider or get_runtime_supervisor_provider()
        self._tasks: dict[str, TaskWorkflow] = {}
        self._agent_tasks: dict[tuple[str, str], TaskWorkflow] = {}

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

        provider_transition = await self.provider.transition(
            workflow.handle,
            phase_id=str(phase["id"]),
        )

        progress = phase["progress"]
        terminal: TerminationResult | None = None
        if status in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            terminal = await self.provider.terminate(
                workflow.handle,
                reason=status.value.casefold(),
            )
            self._tasks.pop(task_id, None)
            self._agent_tasks.pop((task_id, workflow.handle.agent_id), None)
            secondary = [
                (key, item) for key, item in self._agent_tasks.items()
                if key[0] == task_id
            ]
            for key, item in secondary:
                await self.provider.terminate(
                    item.handle,
                    reason=status.value.casefold(),
                )
                self._agent_tasks.pop(key, None)
        return PhaseTransition(
            phase_id=phase["id"],
            label=phase["label"],
            progress=current_progress if progress == "inherit" else progress,
            session_id=workflow.handle.session_id,
            saga_id=workflow.handle.workflow_id,
            supervision={
                "provider": self.provider.provider_id,
                "provider_version": getattr(self.provider, "provider_version", "unknown"),
                "capabilities": asdict(self.provider.capabilities),
                "tier": workflow.handle.tier.value,
                "trust_score": workflow.handle.trust_score,
                "transition": asdict(provider_transition),
                "termination": asdict(terminal) if terminal else None,
            },
        )

    async def before_action(
        self,
        task_id: str,
        action: ActionSpec,
        agent_id: str | None = None,
    ) -> ActionDecision:
        workflow = (
            self._agent_tasks.get((task_id, agent_id))
            if agent_id
            else self._tasks.get(task_id)
        )
        if workflow is None and agent_id:
            workflow = await self._start_agent(task_id, agent_id)
        if workflow is None:
            raise SupervisionConfigurationError(
                f"Runtime supervision has no active session for task {task_id}"
            )
        decision = await self.provider.before_action(workflow.handle, action)
        if not decision.allowed:
            raise SupervisionDeniedError(decision)
        return decision

    async def elevate(
        self,
        task_id: str,
        *,
        target_tier: ExecutionTier,
        ttl_seconds: int,
        reason: str,
        attestation: str | None = None,
    ) -> ElevationGrant:
        workflow = self._tasks.get(task_id)
        if workflow is None:
            raise SupervisionConfigurationError(
                f"Runtime supervision has no active session for task {task_id}"
            )
        return await self.provider.elevate(
            workflow.handle,
            target_tier=target_tier,
            ttl_seconds=ttl_seconds,
            reason=reason,
            attestation=attestation,
        )

    async def close(self, task_id: str, reason: str) -> None:
        workflows = [
            (key, workflow) for key, workflow in self._agent_tasks.items()
            if key[0] == task_id
        ]
        primary = self._tasks.pop(task_id, None)
        if primary:
            await self.provider.terminate(primary.handle, reason=reason)
        for key, workflow in workflows:
            if workflow is not primary:
                await self.provider.terminate(workflow.handle, reason=reason)
            self._agent_tasks.pop(key, None)

    async def _start(self, task_id: str, agent_id: str) -> TaskWorkflow:
        workflow = await self._start_agent(task_id, agent_id)
        self._tasks[task_id] = workflow
        return workflow

    async def _start_agent(self, task_id: str, agent_id: str) -> TaskWorkflow:
        definition = get_definition("workflows", "sdlc")["data"]
        phases = {
            TaskStatus(phase["status"]): phase
            for phase in definition["phases"]
        }
        agent_definition = get_definition(
            "agents",
            agent_id.removeprefix("did:local:"),
        )["data"]
        promotion = agent_definition.get("promotion") or {}
        trust_score = float(
            promotion.get(
                "overall_score",
                get_settings().runtime_supervisor_default_trust,
            )
        )
        handle = await self.provider.start(
            task_id=task_id if task_id not in self._tasks else f"{task_id}:{agent_id}",
            agent_id=agent_id,
            trust_score=trust_score,
            phases=list(phases.values()),
        )
        workflow = TaskWorkflow(handle=handle, phases=phases)
        self._agent_tasks[(task_id, agent_id)] = workflow
        return workflow
