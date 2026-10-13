from dataclasses import dataclass, field
from typing import Any

from .tiers import ExecutionTier


@dataclass(frozen=True)
class SessionHandle:
    provider: str
    session_id: str
    agent_id: str
    tier: ExecutionTier
    trust_score: float
    workflow_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
