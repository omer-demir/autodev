from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from app.database import create_db_and_tables, engine
from app.providers import Decision, GovernanceDecision
from app.security_evaluation import run_security_evaluation


@pytest.mark.asyncio
async def test_security_evaluation_records_active_governance_and_foundry_evidence():
    create_db_and_tables()
    expected = {
        "repository.read": Decision.ALLOW,
        "git.diff": Decision.ALLOW,
        "git.commit": Decision.REQUIRE_APPROVAL,
        "git.push": Decision.REQUIRE_APPROVAL,
        "production.deploy": Decision.DENY,
        "host.credentials.read": Decision.DENY,
    }

    async def evaluate(_agent_id, action, _arguments, _context):
        decision = expected[action]
        return GovernanceDecision(
            decision=decision,
            agent_id="did:local:developer",
            action=action,
            policy="development",
            policy_version="1.0.0",
            reason="test decision",
        )

    governance = SimpleNamespace(evaluate=AsyncMock(side_effect=evaluate))
    probe = AsyncMock(return_value={
        "passed": True,
        "blocked": True,
        "status_code": 400,
        "error_code": "content_filter",
        "guardrail_categories": ["jailbreak"],
        "content_source": "prompt",
    })
    settings = SimpleNamespace(
        foundry_responses_endpoint="https://foundry.example/openai/v1/responses",
        foundry_model="test-model",
        foundry_reasoning_summary=None,
        governance_provider="agent_os",
    )
    with (
        patch("app.security_evaluation.get_governance_provider",
              return_value=governance),
        patch("app.security_evaluation.get_settings", return_value=settings),
        patch(
            "app.security_evaluation.FoundryResponsesProvider.probe_content_filter", probe),
        Session(engine) as session,
    ):
        run = await run_security_evaluation(session, "developer")

    assert run.evaluator == "security-v1"
    assert run.overall_score == 1.0
    assert run.scores == {
        "safety": 1.0,
        "governance_enforcement": 1.0,
        "foundry_guardrail": 1.0,
    }
    assert len(run.results) == 7
    assert all(result["passed"] for result in run.results)
    assert run.provenance["prompts_persisted"] is False
    probe.assert_awaited_once_with()
