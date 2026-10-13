from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdapterResult:
    adapter: str
    passed: bool
    score: float
    duration_seconds: float
    results: list[dict[str, Any]]
    metrics: dict[str, Any]
    evidence_path: str
    version: str | None = None
    error: str | None = None
