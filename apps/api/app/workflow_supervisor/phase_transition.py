from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PhaseTransition:
    phase_id: str
    label: str
    progress: int
    session_id: str
    saga_id: str | None
    supervision: dict[str, Any] = field(default_factory=dict)
