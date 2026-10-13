from ..tiers import ExecutionTier
from .specification import ActionSpec


def required_tier_for(action: ActionSpec) -> ExecutionTier:
    if action.is_admin:
        return ExecutionTier.ROOT
    if not action.reversible and not action.read_only:
        return ExecutionTier.PRIVILEGED
    if action.read_only:
        return ExecutionTier.SANDBOX
    return ExecutionTier.STANDARD
