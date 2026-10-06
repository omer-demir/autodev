from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session

from .config import get_settings
from .foundry import FoundryApiError, FoundryResponsesProvider
from .harness import resolve_agent_harness
from .models import EvaluationRun
from .providers import get_governance_provider
from .registry import RegistryError, get_definition


def _governance_cases(agent_id: str) -> tuple[str, list[dict[str, str]]]:
    catalog = resolve_agent_harness(agent_id)["resolved_capability_catalog"]
    value = catalog["capabilities"]
    cases: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or not all(item.get(key) for key in ("name", "action", "expected")):
            raise RegistryError(
                "Governance capability cases require name, action, and expected")
        cases.append({key: str(item[key])
                     for key in ("name", "action", "expected")})
    return str(catalog["version"]), cases


async def _simulate_rogue_agent(
    agent_id: str, cases: list[dict[str, str]]
) -> list[dict[str, Any]]:
    governance = get_governance_provider()
    results = []
    for case in cases:
        decision = await governance.evaluate(
            f"did:local:{agent_id}",
            case["action"],
            {"simulation": "rogue-agent", "attempted_policy_bypass": True},
            {"task_id": "SECURITY-PROBE", "security_simulation": True},
        )
        actual = str(decision.decision)
        results.append({
            "id": case["name"],
            "type": "rogue-agent",
            "action": case["action"],
            "expected": case["expected"],
            "actual": actual,
            "passed": actual == case["expected"],
            "policy": decision.policy,
            "policy_version": decision.policy_version,
        })
    return results


async def _probe_foundry() -> dict[str, Any]:
    settings = get_settings()
    if not settings.foundry_responses_endpoint:
        return {
            "id": "foundry-content-filter",
            "type": "provider-guardrail",
            "status": "SKIPPED",
            "passed": False,
            "reason": "Microsoft Foundry endpoint is not configured",
        }
    provider = FoundryResponsesProvider(
        endpoint=settings.foundry_responses_endpoint,
        model=settings.foundry_model,
        reasoning_summary=settings.foundry_reasoning_summary,
    )
    try:
        result = await provider.probe_content_filter()
    except (FoundryApiError, RuntimeError) as exc:
        return {
            "id": "foundry-content-filter",
            "type": "provider-guardrail",
            "status": "ERROR",
            "passed": False,
            "error_type": type(exc).__name__,
        }
    return {
        "id": "foundry-content-filter",
        "type": "provider-guardrail",
        "status": "COMPLETED",
        **result,
    }


async def run_security_evaluation(
    session: Session,
    agent_id: str,
    *,
    include_foundry: bool = True,
    organization_id: str = "local",
    created_by: str | None = None,
) -> EvaluationRun:
    agent = get_definition("agents", agent_id)["data"]
    suite_version, cases = _governance_cases(agent_id)
    governance_results = await _simulate_rogue_agent(agent_id, cases)
    foundry_result = await _probe_foundry() if include_foundry else None
    results = [*governance_results, *
               ([foundry_result] if foundry_result else [])]
    passed = sum(bool(item["passed"]) for item in results)
    governance_score = sum(bool(item["passed"]) for item in governance_results) / len(
        governance_results
    )
    overall_score = passed / len(results)
    run = EvaluationRun(
        id=f"EVAL-{uuid4().hex[:12].upper()}",
        agent_id=agent_id,
        agent_version=str(agent["version"]),
        suite_id="security-probes",
        suite_version=suite_version,
        evaluator="security-v1",
        organization_id=organization_id,
        created_by=created_by,
        overall_score=round(overall_score, 4),
        scores={
            "safety": round(overall_score, 4),
            "governance_enforcement": round(governance_score, 4),
            "foundry_guardrail": (
                float(bool(foundry_result["passed"])
                      ) if foundry_result else None
            ),
        },
        results=results,
        provenance={
            "execution": "active-security-probe",
            "agent_executed": False,
            "governance_provider": get_settings().governance_provider,
            "foundry_requested": include_foundry,
            "prompts_persisted": False,
        },
        completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
