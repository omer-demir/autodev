from abc import ABC, abstractmethod
from typing import Any

from .decision_result import GovernanceDecision


class GovernanceProvider(ABC):
    @abstractmethod
    async def evaluate(
        self,
        agent_id: str,
        action: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> GovernanceDecision:
        pass

    @abstractmethod
    async def terminate(self, session_id: str, reason: str) -> None:
        pass
