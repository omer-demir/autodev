from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .tiers import ExecutionTier


@dataclass(frozen=True)
class ElevationGrant:
    provider: str
    grant_id: str
    original_tier: ExecutionTier
    elevated_tier: ExecutionTier
    expires_at: datetime
    evidence: dict[str, Any] = field(default_factory=dict)
