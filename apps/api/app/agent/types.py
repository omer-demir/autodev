from collections.abc import Awaitable, Callable
from typing import Any

from ..model_recovery import ModelRecoveryDecision

EventCallback = Callable[
    [str, str, str, str, dict[str, Any] | None], Awaitable[None]
]
SteeringProvider = Callable[[], Awaitable[list[str]]]
ModelRecovery = Callable[[str, str, int], Awaitable[ModelRecoveryDecision]]
