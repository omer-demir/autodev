from typing import Any, ClassVar

from ...capabilities import SUPPORTED_CAPABILITIES
from ...registry import RegistryError, get_definition
from .decision import Decision
from .decision_result import GovernanceDecision
from .provider import GovernanceProvider


class LocalGovernanceProvider(GovernanceProvider):
    """Local default-deny governance boundary for agent tool execution."""

    allowed: ClassVar[set[str]] = {
        "repository.read",
        "repository.write",
        "filesystem.read",
        "filesystem.write",
        "test.run",
        "build.run",
        "dependency.install",
        "security.scan",
        "git.status",
        "git.diff",
    }
    approval: ClassVar[set[str]] = {
        "git.commit",
        "git.push",
        "pull_request.create",
    }
    supported: ClassVar[frozenset[str]] = SUPPORTED_CAPABILITIES

    async def evaluate(
        self,
        agent_id: str,
        action: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> GovernanceDecision:
        del arguments, context
        try:
            agent = get_definition(
                "agents", agent_id.removeprefix("did:local:")
            )["data"]
        except RegistryError:
            return GovernanceDecision(
                Decision.DENY,
                agent_id,
                action,
                "development-v1",
                "1.0",
                "Default-deny: agent identity is not registered",
            )
        policy_id = str(agent.get("policy", "development"))
        try:
            policy = get_definition("policies", policy_id)["data"]
        except RegistryError:
            return GovernanceDecision(
                Decision.DENY,
                agent_id,
                action,
                policy_id,
                "unknown",
                "Default-deny: agent governance policy is not registered",
            )
        policy_decision = str(policy.get("default_action", "deny"))
        for rule in policy.get("rules", []):
            if action in set(rule.get("capabilities", [])):
                policy_decision = str(rule["decision"])
                break
        policy_name = str(policy.get("name", policy_id))
        policy_version = str(policy.get("version", "unknown"))
        if action in set(agent.get("deny", [])) or policy_decision == "deny":
            decision, reason = Decision.DENY, "Capability is explicitly denied for this agent"
        elif action in set(agent.get("approval", [])) or policy_decision == "require_approval":
            decision = Decision.REQUIRE_APPROVAL
            reason = "Agent capability requires human approval"
        elif action in set(agent.get("capabilities", [])) and policy_decision == "allow":
            decision, reason = Decision.ALLOW, "Capability granted by the agent declaration"
        else:
            decision = Decision.DENY
            reason = "Default-deny: capability is not granted to this agent"
        return GovernanceDecision(
            decision,
            agent_id,
            action,
            policy_name,
            policy_version,
            reason,
        )

    async def terminate(self, session_id: str, reason: str) -> None:
        del session_id, reason
