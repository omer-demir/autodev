from dataclasses import asdict
from importlib.metadata import version
from typing import Any

from ..actions import ActionDecision, ActionSpec
from ..capabilities import ProviderCapabilities
from ..elevations import ElevationGrant
from ..errors import (
    SupervisionConfigurationError,
    SupervisionDeniedError,
    SupervisionElevationError,
)
from ..provider import RuntimeSupervisorProvider
from ..sessions import SessionHandle
from ..terminations import TerminationResult
from ..tiers import ExecutionTier
from ..transitions import TransitionResult
from ..utils import bounded_score, serializable
from .microsoft_session import MicrosoftSession
from .microsoft_support import action_descriptor, kill_reason, terminal_commitment


class MicrosoftAgentHypervisorProvider(RuntimeSupervisorProvider):
    provider_id = "microsoft_agent_hypervisor"
    provider_version = version("agent-governance-toolkit-core")
    capabilities = ProviderCapabilities(
        dynamic_rings=True,
        ttl_elevation=True,
        saga_compensation=True,
        per_ring_rate_limits=True,
        breach_detection=True,
        kill_handoff=True,
        audit_commitment=True,
    )

    def __init__(
        self,
        *,
        hypervisor: Any | None = None,
        rate_limiter: Any | None = None,
        breach_detector: Any | None = None,
        elevation_manager: Any | None = None,
        kill_switch: Any | None = None,
    ) -> None:
        from hypervisor import Hypervisor
        from hypervisor.rings.breach_detector import RingBreachDetector
        from hypervisor.rings.elevation import RingElevationManager
        from hypervisor.security.kill_switch import KillSwitch
        from hypervisor.security.rate_limiter import AgentRateLimiter

        self.hypervisor = hypervisor or Hypervisor()
        self.rate_limiter = rate_limiter or AgentRateLimiter()
        self.breach_detector = breach_detector or RingBreachDetector()
        self.elevation_manager = elevation_manager or RingElevationManager()
        self.kill_switch = kill_switch or KillSwitch()
        self._sessions: dict[str, MicrosoftSession] = {}

    async def start(
        self,
        *,
        task_id: str,
        agent_id: str,
        trust_score: float,
        phases: list[dict[str, Any]],
    ) -> SessionHandle:
        from hypervisor.models import SessionConfig

        score = bounded_score(trust_score)
        managed = await self.hypervisor.create_session(
            SessionConfig(max_participants=1, enable_audit=True),
            creator_did=agent_id,
        )
        session_id = managed.sso.session_id
        ring = await self.hypervisor.join_session(
            session_id,
            agent_id,
            sigma_raw=score,
        )
        await self.hypervisor.activate_session(session_id)
        saga = managed.saga.create_saga(session_id)
        step_ids: dict[str, str] = {}
        for phase in phases:
            phase_id = str(phase["id"])
            step = managed.saga.add_step(
                saga.saga_id,
                action_id=f"workflow.{phase_id}",
                agent_did=agent_id,
                execute_api=f"workflow://{phase_id}",
                undo_api=f"workflow://{phase_id}/undo",
                timeout_seconds=300,
                max_retries=1,
            )
            step_ids[phase_id] = step.step_id

        handle = SessionHandle(
            provider=self.provider_id,
            session_id=session_id,
            agent_id=agent_id,
            tier=ExecutionTier(ring.value),
            trust_score=score,
            workflow_id=saga.saga_id,
            metadata={"task_id": task_id},
        )
        self._sessions[task_id] = MicrosoftSession(
            handle=handle,
            saga_id=saga.saga_id,
            step_ids=step_ids,
        )
        self.kill_switch.register_agent(agent_id, lambda: None)
        return handle

    async def before_action(
        self,
        handle: SessionHandle,
        action: ActionSpec,
    ) -> ActionDecision:
        from hypervisor.models import ExecutionRing
        from hypervisor.security.rate_limiter import RateLimitExceeded

        managed = self.hypervisor.get_session(handle.session_id)
        if managed is None:
            raise SupervisionConfigurationError(
                f"Runtime supervision session {handle.session_id} is unavailable"
            )

        participant = managed.sso.get_participant(handle.agent_id)
        base_ring = participant.ring
        self.elevation_manager.tick()
        effective_ring = self.elevation_manager.get_effective_ring(
            handle.agent_id,
            handle.session_id,
            base_ring,
        )
        descriptor = action_descriptor(action)
        check = self.hypervisor.ring_enforcer.check(
            effective_ring,
            descriptor,
            participant.eff_score,
        )
        if check.allowed and action.command:
            command_check = self.hypervisor.ring_enforcer.check_command(
                action.command)
            check.allowed = command_check.allowed
            check.reason = command_check.reason

        # Same-tier tool volume is governed by the per-ring rate limiter. The
        # upstream breach detector estimates early rates from only two samples,
        # so recording normal back-to-back writes can falsely and permanently
        # trip a session. Reserve breach detection for actual upward ring
        # attempts; all actions remain ring-checked and rate-limited.
        breach = None
        if descriptor.required_ring < effective_ring:
            breach = self.breach_detector.record_call(
                handle.agent_id,
                handle.session_id,
                effective_ring,
                descriptor.required_ring,
            )
        evidence: dict[str, Any] = {
            "base_tier": base_ring.value,
            "effective_tier": effective_ring.value,
            "trust_score": participant.eff_score,
        }
        if breach is not None:
            evidence["breach"] = serializable(asdict(breach))

        if self.breach_detector.is_breaker_tripped(
            handle.agent_id,
            handle.session_id,
        ):
            active_elevation = self.elevation_manager.get_active_elevation(
                handle.agent_id,
                handle.session_id,
            )
            if active_elevation is not None:
                self.elevation_manager.revoke_elevation(
                    active_elevation.elevation_id)
            participant.ring = ExecutionRing.RING_3_SANDBOX
            self.rate_limiter.update_ring(
                handle.agent_id,
                handle.session_id,
                ExecutionRing.RING_3_SANDBOX,
            )
            severity = breach.severity.value if breach is not None else "tripped"
            decision = ActionDecision(
                allowed=False,
                provider=self.provider_id,
                capability=action.capability,
                agent_tier=ExecutionTier(effective_ring.value),
                required_tier=ExecutionTier(descriptor.required_ring.value),
                reason=f"Ring breach circuit breaker tripped: {severity}",
                evidence={**evidence,
                          "demoted_tier": ExecutionTier.SANDBOX.value},
            )
            raise SupervisionDeniedError(decision)

        if not check.allowed:
            decision = ActionDecision(
                allowed=False,
                provider=self.provider_id,
                capability=action.capability,
                agent_tier=ExecutionTier(effective_ring.value),
                required_tier=ExecutionTier(descriptor.required_ring.value),
                reason=check.reason,
                evidence=evidence,
            )
            raise SupervisionDeniedError(decision)

        try:
            self.rate_limiter.check(
                handle.agent_id,
                handle.session_id,
                effective_ring,
            )
        except RateLimitExceeded as exc:
            decision = ActionDecision(
                allowed=False,
                provider=self.provider_id,
                capability=action.capability,
                agent_tier=ExecutionTier(effective_ring.value),
                required_tier=ExecutionTier(descriptor.required_ring.value),
                reason=str(exc),
                evidence={**evidence, "rate_limited": True},
            )
            raise SupervisionDeniedError(decision) from exc

        return ActionDecision(
            allowed=True,
            provider=self.provider_id,
            capability=action.capability,
            agent_tier=ExecutionTier(effective_ring.value),
            required_tier=ExecutionTier(descriptor.required_ring.value),
            reason=check.reason,
            evidence=evidence,
        )

    async def transition(
        self,
        handle: SessionHandle,
        *,
        phase_id: str,
    ) -> TransitionResult:
        state = self._session_state(handle)
        step_id = state.step_ids[phase_id]
        if phase_id not in state.completed_steps:
            managed = self.hypervisor.get_session(handle.session_id)
            if managed is None:
                raise SupervisionConfigurationError(
                    f"Runtime supervision session {handle.session_id} is unavailable"
                )

            async def _complete() -> dict[str, str]:
                return {"phase_id": phase_id}

            await managed.saga.execute_step(state.saga_id, step_id, _complete)
            state.completed_steps.add(phase_id)
        return TransitionResult(
            provider=self.provider_id,
            phase_id=phase_id,
            saga_id=state.saga_id,
            step_id=step_id,
        )

    async def elevate(
        self,
        handle: SessionHandle,
        *,
        target_tier: ExecutionTier,
        ttl_seconds: int,
        reason: str,
        attestation: str | None = None,
    ) -> ElevationGrant:
        from hypervisor.models import ExecutionRing
        from hypervisor.rings.elevation import RingElevationError

        managed = self.hypervisor.get_session(handle.session_id)
        if managed is None:
            raise SupervisionConfigurationError(
                f"Runtime supervision session {handle.session_id} is unavailable"
            )
        participant = managed.sso.get_participant(handle.agent_id)
        try:
            elevation = self.elevation_manager.request_elevation(
                handle.agent_id,
                handle.session_id,
                participant.ring,
                ExecutionRing(target_tier.value),
                ttl_seconds=ttl_seconds,
                attestation=attestation,
                reason=reason,
                trust_score=participant.eff_score,
            )
        except RingElevationError as exc:
            raise SupervisionElevationError(str(exc)) from exc
        self.rate_limiter.update_ring(
            handle.agent_id,
            handle.session_id,
            elevation.elevated_ring,
        )
        return ElevationGrant(
            provider=self.provider_id,
            grant_id=elevation.elevation_id,
            original_tier=ExecutionTier(elevation.original_ring.value),
            elevated_tier=ExecutionTier(elevation.elevated_ring.value),
            expires_at=elevation.expires_at,
            evidence={"reason": elevation.reason},
        )

    async def terminate(
        self,
        handle: SessionHandle,
        *,
        reason: str,
    ) -> TerminationResult:
        from hypervisor.security.kill_switch import KillReason

        state = self._session_state(handle)
        managed = self.hypervisor.get_session(handle.session_id)
        in_flight: list[dict[str, str]] = []
        saga_compensated = False
        if managed is not None:
            saga = managed.saga.get_saga(state.saga_id)
            if saga is not None:
                in_flight = [
                    {"step_id": step.step_id, "saga_id": state.saga_id}
                    for step in saga.steps
                    if step.action_id.removeprefix("workflow.") not in state.completed_steps
                ]
                if reason not in {"done", "completed"} and saga.committed_steps_reversed:
                    async def _compensate(step: Any) -> dict[str, str]:
                        return {"undo_api": str(step.undo_api)}

                    await managed.saga.compensate(state.saga_id, _compensate)
                    saga_compensated = True

        kill = self.kill_switch.kill(
            handle.agent_id,
            handle.session_id,
            kill_reason(reason, KillReason),
            in_flight_steps=in_flight,
            details=reason,
        )
        audit_commitment = await self.hypervisor.terminate_session(handle.session_id)
        commitment_source = "agent_hypervisor_delta_chain"
        if audit_commitment is None:
            commitment_source = "autodev_terminal_evidence"
            audit_commitment = terminal_commitment(handle, reason, kill)
        self._sessions.pop(str(handle.metadata.get("task_id", "")), None)
        return TerminationResult(
            provider=self.provider_id,
            reason=reason,
            audit_commitment=audit_commitment,
            terminated=kill.terminated,
            compensation_triggered=kill.compensation_triggered or saga_compensated,
            handoffs=tuple(serializable(asdict(item))
                           for item in kill.handoffs),
            evidence={
                "kill_id": kill.kill_id,
                "audit_commitment_source": commitment_source,
            },
        )

    def _session_state(self, handle: SessionHandle) -> MicrosoftSession:
        task_id = str(handle.metadata.get("task_id", ""))
        state = self._sessions.get(task_id)
        if state is None:
            raise SupervisionConfigurationError(
                f"Runtime supervision state for task {task_id or '<unknown>'} is unavailable"
            )
        return state
