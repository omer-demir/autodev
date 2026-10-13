from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TerminationResult:
    provider: str
    reason: str
    audit_commitment: str | None = None
    terminated: bool = True
    compensation_triggered: bool = False
    handoffs: tuple[dict[str, Any], ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
