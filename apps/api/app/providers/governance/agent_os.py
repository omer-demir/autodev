from typing import Any

from .decision import Decision
from .decision_result import GovernanceDecision
from .local import LocalGovernanceProvider
from .provider import GovernanceProvider


class AgentOSGovernanceProvider(GovernanceProvider):
    """Enforce the effective Workbench decision through Agent OS."""

    def __init__(self, local: GovernanceProvider | None = None) -> None:
        try:
            from agent_os.stateless import ExecutionContext, StatelessKernel
        except ImportError as exc:
            raise RuntimeError(
                "Agent OS governance is configured but agent-governance-toolkit-core "
                "is not installed"
            ) from exc
        self.local = local or LocalGovernanceProvider()
        self._context_type = ExecutionContext
        self._kernel_type = StatelessKernel

    async def evaluate(
        self,
        agent_id: str,
        action: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> GovernanceDecision:
        effective = await self.local.evaluate(agent_id, action, arguments, context)
        policy_id = "autodev-effective-policy"
        policy: dict[str, list[str]] = {}
        if effective.decision is Decision.DENY:
            policy["blocked_actions"] = [action]
        elif effective.decision is Decision.REQUIRE_APPROVAL:
            policy["require_approval"] = [action]

        try:
            kernel = self._kernel_type(policies={policy_id: policy})
            result = await kernel.execute(
                action=action,
                params=arguments,
                context=self._context_type(
                    agent_id=agent_id,
                    policies=[policy_id],
                    metadata=context,
                ),
            )
        except Exception as exc:
            return GovernanceDecision(
                Decision.DENY,
                agent_id,
                action,
                effective.policy,
                effective.policy_version,
                f"Agent OS enforcement failed closed: {type(exc).__name__}",
            )

        if result.success and effective.decision is Decision.ALLOW:
            return effective
        if not result.success and effective.decision is Decision.REQUIRE_APPROVAL:
            return effective
        reason = result.error or "Agent OS rejected the effective governance decision"
        return GovernanceDecision(
            Decision.DENY,
            agent_id,
            action,
            effective.policy,
            effective.policy_version,
            f"Agent OS denied the action: {reason}",
        )

    async def terminate(self, session_id: str, reason: str) -> None:
        await self.local.terminate(session_id, reason)
