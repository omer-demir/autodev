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
    "capability",
    ["git.commit", "git.push", "pull_request.create"],
)
async def test_architect_changes_use_human_approval_gates(capability: str):
    result = await LocalGovernanceProvider().evaluate(
        "did:local:architect", capability, {}, {"task_id": "TASK-ADR"}
    )

    assert result.decision is Decision.REQUIRE_APPROVAL


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
