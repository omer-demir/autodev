from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransitionResult:
    provider: str
    phase_id: str
    saga_id: str | None = None
    step_id: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
