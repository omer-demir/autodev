from dataclasses import dataclass

from .decision import Decision


@dataclass(frozen=True)
class GovernanceDecision:
    decision: Decision
    agent_id: str
    action: str
    policy: str
    policy_version: str
    reason: str
