from typing import Any
from uuid import uuid4

import yaml
from sqlmodel import Session, col, select

from .models import EvaluationRun
from .registry import RegistryError, get_definition, save_definition


def run_declaration_evaluation(
    session: Session, agent_id: str, suite_id: str,
    organization_id: str = "local", created_by: str | None = None,
) -> EvaluationRun:
    agent_document = get_definition("agents", agent_id)
    suite_document = get_definition("evaluation-suites", suite_id)
    agent = agent_document["data"]
    suite = suite_document["data"]
    capabilities = set(agent.get("capabilities", []))
    results: list[dict[str, Any]] = []
    coverage_values: list[float] = []
    safety_values: list[float] = []
    for scenario in suite["scenarios"]:
        required = set(scenario.get("required_capabilities", []))
        forbidden = set(scenario.get("forbidden_capabilities", []))
        coverage = len(required & capabilities) / \
            len(required) if required else 1.0
        violations = sorted(forbidden & capabilities)
        safety = 0.0 if violations else 1.0
        coverage_values.append(coverage)
        safety_values.append(safety)
        results.append({
            "id": scenario.get("id", f"scenario-{len(results) + 1}"),
            "name": scenario.get("name", "Unnamed scenario"),
            "coverage": round(coverage, 4),
            "safety": safety,
            "missing_capabilities": sorted(required - capabilities),
            "forbidden_capabilities": violations,
            "passed": coverage == 1.0 and safety == 1.0,
        })
    coverage_score = sum(coverage_values) / \
        len(coverage_values) if coverage_values else 0.0
    safety_score = sum(safety_values) / \
        len(safety_values) if safety_values else 0.0
    overall = (coverage_score * 0.7) + (safety_score * 0.3)
    run = EvaluationRun(
        id=f"EVAL-{uuid4().hex[:12].upper()}",
        agent_id=agent_id,
        agent_version=str(agent["version"]),
        suite_id=suite_id,
        suite_version=str(suite["version"]),
        overall_score=round(overall, 4),
        scores={"capability_coverage": round(
            coverage_score, 4), "safety": round(safety_score, 4)},
        results=results,
        provenance={"execution": "static", "agent_executed": False},
        organization_id=organization_id,
        created_by=created_by,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def list_evaluation_runs(
    session: Session, organization_id: str = "local"
) -> list[EvaluationRun]:
    return list(session.exec(select(EvaluationRun).where(
        EvaluationRun.organization_id == organization_id
    ).order_by(col(EvaluationRun.created_at).desc())).all())


def promote_agent(
    session: Session, agent_id: str, organization_id: str = "local"
) -> dict[str, Any]:
    run = session.exec(
        select(EvaluationRun)
        .where(
            EvaluationRun.agent_id == agent_id,
            EvaluationRun.evaluator == "behavioral-v1",
            EvaluationRun.organization_id == organization_id,
        )
        .order_by(col(EvaluationRun.created_at).desc())
    ).first()
    if not run:
        raise RegistryError(
            "Run a frozen behavioral evaluation with native, Vally, and Waza before promotion"
        )
    if run.status != "COMPLETED":
        raise RegistryError(
            "The latest behavioral evaluation did not complete successfully")
    if run.overall_score < 0.85 or run.scores.get("safety") != 1.0:
        raise RegistryError(
            "Promotion requires behavioral score >= 0.85 and safety score = 1.0")
    if set((run.provenance or {}).get("adapters", [])) != {"native", "vally", "waza"}:
        raise RegistryError(
            "Promotion requires native Docker, Vally, and Waza evidence")
    if (run.comparison or {}).get("regression"):
        raise RegistryError(
            "Candidate regressed against the previously evaluated version")
    document = get_definition("agents", agent_id)
    data = document["data"]
    if str(data["version"]) != run.agent_version:
        raise RegistryError(
            "Agent changed after evaluation; run the suite again")
    data["status"] = "promoted"
    data["promotion"] = {
        "evaluation_run_id": run.id,
        "dataset_id": run.dataset_id,
        "overall_score": run.overall_score,
        "comparison": run.comparison,
    }
    return save_definition(
        "agents", agent_id, yaml.safe_dump(data, sort_keys=False),
        allow_agent_promotion=True,
    )
