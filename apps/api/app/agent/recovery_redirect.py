from ..model_recovery import ModelRecoveryDecision


class ModelRecoveryRedirect(Exception):
    def __init__(self, decision: ModelRecoveryDecision, error: str) -> None:
        super().__init__(error)
        self.decision = decision
        self.error = error
