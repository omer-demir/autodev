from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..actions import ActionDecision


class SupervisionDeniedError(RuntimeError):
    def __init__(self, decision: "ActionDecision") -> None:
        super().__init__(decision.reason)
        self.decision = decision
