from dataclasses import dataclass, field
from typing import Any

from ..tiers import ExecutionTier


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    provider: str
    capability: str
    agent_tier: ExecutionTier
    required_tier: ExecutionTier
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
