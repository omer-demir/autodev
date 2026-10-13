from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRecoveryDecision:
    action: str
    model: str | None = None
