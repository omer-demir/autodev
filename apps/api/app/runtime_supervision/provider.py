from abc import ABC, abstractmethod
from typing import Any

from .actions import ActionDecision, ActionSpec
from .capabilities import ProviderCapabilities
from .elevations import ElevationGrant
from .sessions import SessionHandle
from .terminations import TerminationResult
from .tiers import ExecutionTier
from .transitions import TransitionResult


class RuntimeSupervisorProvider(ABC):
    provider_id: str
    provider_version: str
    capabilities: ProviderCapabilities

    @abstractmethod
    async def start(
        self,
        *,
        task_id: str,
        agent_id: str,
        trust_score: float,
        phases: list[dict[str, Any]],
    ) -> SessionHandle:
        pass

    @abstractmethod
    async def before_action(
        self,
        handle: SessionHandle,
        action: ActionSpec,
    ) -> ActionDecision:
        pass

    @abstractmethod
    async def transition(
        self,
        handle: SessionHandle,
        *,
        phase_id: str,
    ) -> TransitionResult:
        pass

    @abstractmethod
    async def elevate(
        self,
        handle: SessionHandle,
        *,
        target_tier: ExecutionTier,
        ttl_seconds: int,
        reason: str,
        attestation: str | None = None,
    ) -> ElevationGrant:
        pass

    @abstractmethod
    async def terminate(
        self,
        handle: SessionHandle,
        *,
        reason: str,
    ) -> TerminationResult:
        pass
