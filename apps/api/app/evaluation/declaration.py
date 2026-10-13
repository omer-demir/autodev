from typing import Any
from uuid import uuid4

from sqlmodel import Session

from ..models import EvaluationDataset, EvaluationRun
from ..registry import RegistryError, get_definition


def run_declaration_evaluation(
    session: Session,
    agent_id: str,
    dataset_id: str,
    organization_id: str = "local",
    created_by: str | None = None,
) -> EvaluationRun:
    agent_document = get_definition("agents", agent_id)
    agent = agent_document["data"]
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != organization_id:
        raise RegistryError("Evaluation dataset not found")
    capabilities = set(agent.get("capabilities", []))
    results: list[dict[str, Any]] = []
    coverage_values: list[float] = []
    safety_values: list[float] = []
    for scenario in dataset.scenarios:
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
    coverage_score = (
        sum(coverage_values) / len(coverage_values) if coverage_values else 0.0
    )
    safety_score = sum(safety_values) / \
        len(safety_values) if safety_values else 0.0
    overall = (coverage_score * 0.7) + (safety_score * 0.3)
    run = EvaluationRun(
        id=f"EVAL-{uuid4().hex[:12].upper()}",
        agent_id=agent_id,
        agent_version=str(agent["version"]),
        suite_id=dataset.suite_id,
        suite_version=dataset.suite_version,
        dataset_id=dataset.id,
        overall_score=round(overall, 4),
        scores={
            "capability_coverage": round(coverage_score, 4),
            "safety": round(safety_score, 4),
        },
        results=results,
        provenance={
            "execution": "static", "agent_executed": False,
            "dataset_hash": dataset.content_hash,
        },
        organization_id=organization_id,
        created_by=created_by,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
