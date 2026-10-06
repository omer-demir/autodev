import pytest

from app.providers import AgentOSGovernanceProvider, Decision, LocalGovernanceProvider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        ("repository.read", Decision.ALLOW),
        ("git.diff", Decision.ALLOW),
        ("git.commit", Decision.REQUIRE_APPROVAL),
        ("git.push", Decision.REQUIRE_APPROVAL),
        ("production.deploy", Decision.DENY),
        ("host.credentials.read", Decision.DENY),
        ("unknown.capability", Decision.DENY),
    ],
)
async def test_default_deny_policy(capability: str, expected: Decision):
    result = await LocalGovernanceProvider().evaluate(
        "did:local:developer", capability, {}, {"task_id": "TASK-001"}
    )
    assert result.decision is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        ("repository.read", Decision.ALLOW),
        ("git.diff", Decision.ALLOW),
        ("git.commit", Decision.REQUIRE_APPROVAL),
        ("git.push", Decision.REQUIRE_APPROVAL),
        ("production.deploy", Decision.DENY),
        ("host.credentials.read", Decision.DENY),
        ("unknown.capability", Decision.DENY),
    ],
)
async def test_agent_os_preserves_effective_policy(capability: str, expected: Decision):
    result = await AgentOSGovernanceProvider().evaluate(
        "did:local:developer", capability, {}, {"task_id": "TASK-001"}
    )
    assert result.decision is expected
