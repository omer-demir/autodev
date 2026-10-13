from datetime import datetime
from typing import Any


def bounded_score(score: float) -> float:
    return max(0.0, min(float(score), 1.0))


def serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
