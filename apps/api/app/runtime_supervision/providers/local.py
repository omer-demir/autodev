from typing import Any

from ..actions import ActionDecision, ActionSpec, required_tier_for
from ..capabilities import ProviderCapabilities
from ..elevations import ElevationGrant
from ..errors import SupervisionConfigurationError
from ..provider import RuntimeSupervisorProvider
from ..sessions import SessionHandle
from ..terminations import TerminationResult
from ..tiers import ExecutionTier
from ..transitions import TransitionResult
from ..utils import bounded_score


class LocalRuntimeSupervisor(RuntimeSupervisorProvider):
    provider_id = "local"
    provider_version = "1.0"
    capabilities = ProviderCapabilities()

    async def start(
        self,
        *,
        task_id: str,
        agent_id: str,
        trust_score: float,
        phases: list[dict[str, Any]],
    ) -> SessionHandle:
        del phases
        return SessionHandle(
            provider=self.provider_id,
            session_id=f"local:{task_id}",
            agent_id=agent_id,
            tier=ExecutionTier.STANDARD,
            trust_score=bounded_score(trust_score),
        )

    async def before_action(
        self,
        handle: SessionHandle,
        action: ActionSpec,
    ) -> ActionDecision:
        required_tier = required_tier_for(action)
        allowed = required_tier != ExecutionTier.ROOT
        return ActionDecision(
            allowed=allowed,
            provider=self.provider_id,
            capability=action.capability,
            agent_tier=handle.tier,
            required_tier=required_tier,
            reason="Portable supervision permits the action"
            if allowed
            else "Root-tier actions require an enforcing runtime supervisor",
        )

    async def transition(
        self,
        handle: SessionHandle,
        *,
        phase_id: str,
    ) -> TransitionResult:
        del handle
        return TransitionResult(provider=self.provider_id, phase_id=phase_id)

    async def elevate(
        self,
        handle: SessionHandle,
        *,
        target_tier: ExecutionTier,
        ttl_seconds: int,
        reason: str,
        attestation: str | None = None,
    ) -> ElevationGrant:
        del handle, target_tier, ttl_seconds, reason, attestation
        raise SupervisionConfigurationError(
            "The local runtime supervisor does not support TTL elevation"
        )

    async def terminate(
        self,
        handle: SessionHandle,
        *,
        reason: str,
    ) -> TerminationResult:
        del handle
        return TerminationResult(provider=self.provider_id, reason=reason)
