import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from ..agent_identity import AgentIdentityError, agent_identity_service
from ..auth import Principal, require_permission
from ..behavioral_evaluation import (
    behavioral_evaluation_readiness,
    cancel_behavioral_evaluation,
    create_evaluation_dataset_version,
    ensure_evaluation_baselines,
    freeze_evaluation_dataset,
    generate_evaluation_dataset,
    list_evaluation_datasets,
    start_behavioral_evaluation,
    update_evaluation_dataset,
)
from ..config import get_settings
from ..database import get_session
from ..evaluation import (
    list_evaluation_runs,
    promote_agent,
    run_declaration_evaluation,
    set_agent_evaluation_requirement,
)
from ..model_catalog import list_provider_models, runtime_model_pricing
from ..models import EvaluationDataset, EvaluationEvent, EvaluationRun
from ..registry import RegistryError, get_definition
from ..schemas import (
    AgentEvaluationRequirement,
    BehavioralEvaluationRunCreate,
    EvaluationDatasetCreate,
    EvaluationDatasetFreeze,
    EvaluationDatasetUpdate,
    EvaluationDatasetVersionCreate,
    EvaluationRunCreate,
    SecurityEvaluationRunCreate,
)
from ..security_evaluation import run_security_evaluation
from ..telemetry import build_agent_telemetry


router = APIRouter(tags=["evaluations"])


@router.get("/api/evaluations")
def evaluations(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return list_evaluation_runs(session, principal.organization_id)


@router.get("/api/evaluations/behavioral/readiness")
async def behavioral_readiness(
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    del principal
    return await behavioral_evaluation_readiness()


@router.get("/api/evaluations/models")
async def evaluation_models(
    provider: str = Query(pattern="^(copilot|ollama)$"),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    del principal
    try:
        models = await list_provider_models(provider)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "provider": provider,
        "models": models,
        "default_model": "auto" if provider == "copilot" else (
            str(models[0].get("name") or models[0].get("id"))
            if models else None
        ),
    }


@router.get("/api/evaluations/{run_id}", response_model=EvaluationRun)
def evaluation_run(
    run_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    run = session.get(EvaluationRun, run_id)
    if not run or run.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation run not found")
    return run


@router.get(
    "/api/evaluations/{run_id}/events",
    response_model=list[EvaluationEvent],
)
def evaluation_events(
    run_id: str,
    after_id: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    run = session.get(EvaluationRun, run_id)
    if not run or run.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation run not found")
    return list(session.exec(
        select(EvaluationEvent).where(
            EvaluationEvent.run_id == run_id,
            EvaluationEvent.organization_id == principal.organization_id,
            EvaluationEvent.id > after_id,
        ).order_by(EvaluationEvent.id).limit(limit)
    ).all())


@router.get("/api/evaluations/{run_id}/artifacts")
def evaluation_artifacts(
    run_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    run = session.get(EvaluationRun, run_id)
    if not run or run.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation run not found")
    root = (Path(get_settings().evidence_dir).resolve() / run_id).resolve()
    files = []
    if root.exists():
        for path in sorted(
            item for item in root.rglob("*") if item.is_file()
        )[:500]:
            resolved = path.resolve()
            if root not in resolved.parents:
                continue
            preview = None
            if path.suffix.casefold() in {
                ".log", ".json", ".jsonl", ".yaml", ".yml", ".md", ".txt"
            }:
                preview = path.read_text(
                    encoding="utf-8", errors="replace"
                )[-30_000:]
                preview = re.sub(
                    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
                    "[REDACTED_GITHUB_TOKEN]",
                    preview,
                )
            files.append({
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "preview": preview,
            })
    return {"run_id": run_id, "files": files}


@router.post(
    "/api/evaluations/{run_id}/cancel",
    response_model=EvaluationRun,
)
async def cancel_evaluation(
    run_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
) -> EvaluationRun:
    run = session.get(EvaluationRun, run_id)
    if not run or run.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation run not found")
    try:
        return await cancel_behavioral_evaluation(
            session, run_id, principal.user_id
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/api/evaluations/run", status_code=201, include_in_schema=False
)
@router.post("/api/evaluations/declaration", status_code=201)
def run_declaration_check(
    payload: EvaluationRunCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    try:
        return run_declaration_evaluation(
            session,
            payload.agent_id,
            payload.dataset_id,
            principal.organization_id,
            principal.user_id,
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/evaluations/security", status_code=201)
async def run_security_check(
    payload: SecurityEvaluationRunCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    try:
        return await run_security_evaluation(
            session,
            payload.agent_id,
            include_foundry=payload.include_foundry,
            organization_id=principal.organization_id,
            created_by=principal.user_id,
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/api/evaluation-datasets", response_model=list[EvaluationDataset]
)
def evaluation_datasets(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return list_evaluation_datasets(session, principal.organization_id)


@router.get("/api/evaluation-datasets/catalog")
def evaluation_dataset_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    query: str = "",
    status: str = "",
    agent_id: str = "",
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    statement = select(EvaluationDataset).where(
        EvaluationDataset.organization_id == principal.organization_id,
        EvaluationDataset.status != "ARCHIVED",
    )
    count_statement = select(func.count()).select_from(
        EvaluationDataset
    ).where(
        EvaluationDataset.organization_id == principal.organization_id,
        EvaluationDataset.status != "ARCHIVED",
    )
    filters = []
    if status:
        filters.append(EvaluationDataset.status == status)
    if agent_id:
        filters.append(EvaluationDataset.agent_id == agent_id)
    if query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(or_(
            EvaluationDataset.id.ilike(pattern),
            EvaluationDataset.dataset_name.ilike(pattern),
            EvaluationDataset.agent_id.ilike(pattern),
            EvaluationDataset.suite_id.ilike(pattern),
        ))
    for condition in filters:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    total = session.exec(count_statement).one()
    items = session.exec(statement.order_by(
        col(EvaluationDataset.updated_at).desc()
    ).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": list(items),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/api/evaluation-datasets/{dataset_id}",
    response_model=EvaluationDataset,
)
def evaluation_dataset(
    dataset_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    return dataset


@router.get(
    "/api/evaluation-datasets/{dataset_id}/versions",
    response_model=list[EvaluationDataset],
)
def evaluation_dataset_versions(
    dataset_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    dataset_name = (
        dataset.dataset_name or f"{dataset.agent_id}-{dataset.suite_id}"
    )
    return list(session.exec(select(EvaluationDataset).where(
        EvaluationDataset.organization_id == principal.organization_id,
        EvaluationDataset.dataset_name == dataset_name,
    ).order_by(col(EvaluationDataset.version).desc())).all())


@router.post(
    "/api/evaluation-datasets",
    response_model=EvaluationDataset,
    status_code=201,
)
def create_evaluation_dataset(
    payload: EvaluationDatasetCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    try:
        agent = get_definition("agents", payload.agent_id)["data"]
        agent_identity_service.enroll(
            session, payload.agent_id, agent, principal
        )
        seed_id = str(agent.get("evaluation_suite") or "baseline")
        return generate_evaluation_dataset(
            session,
            payload.agent_id,
            seed_id,
            payload.generation_model,
            principal.organization_id,
            principal.user_id,
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post(
    "/api/evaluation-datasets/baselines",
    response_model=list[EvaluationDataset],
    status_code=201,
)
def ensure_baseline_evaluation_datasets(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    try:
        return ensure_evaluation_baselines(
            session, principal.organization_id, principal.user_id
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put(
    "/api/evaluation-datasets/{dataset_id}",
    response_model=EvaluationDataset,
)
def review_evaluation_dataset(
    dataset_id: str,
    payload: EvaluationDatasetUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    try:
        return update_evaluation_dataset(
            session,
            dataset_id,
            payload.scenarios,
            payload.reviewed_by,
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/api/evaluation-datasets/{dataset_id}/versions",
    response_model=EvaluationDataset,
    status_code=201,
)
def create_dataset_version(
    dataset_id: str,
    payload: EvaluationDatasetVersionCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    try:
        return create_evaluation_dataset_version(
            session,
            dataset_id,
            payload.scenarios,
            principal.user_id,
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/api/evaluation-datasets/{dataset_id}/freeze",
    response_model=EvaluationDataset,
)
def freeze_dataset(
    dataset_id: str,
    payload: EvaluationDatasetFreeze,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    try:
        return freeze_evaluation_dataset(
            session, dataset_id, payload.reviewed_by
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/evaluations/behavioral", status_code=202)
async def run_behavioral(
    payload: BehavioralEvaluationRunCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    dataset = session.get(EvaluationDataset, payload.dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    try:
        return start_behavioral_evaluation(
            session,
            payload.agent_id,
            payload.dataset_id,
            payload.model_name,
            payload.adapters,
            payload.model_provider,
            payload.verbose_logging,
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/agents/{agent_id}/promote")
def promote(
    agent_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    try:
        promoted = promote_agent(
            session, agent_id, principal.organization_id
        )
        identity = agent_identity_service.enroll(
            session, agent_id, promoted["data"], principal
        )
        return {
            **promoted,
            "agent_did": identity.did,
            "marketplace_verified": True,
        }
    except (AgentIdentityError, RegistryError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/api/agents/{agent_id}/evaluation-requirement")
def set_evaluation_requirement(
    agent_id: str,
    payload: AgentEvaluationRequirement,
    session: Session = Depends(get_session),
    principal: Principal = Depends(
        require_permission("agent.evaluation_bypass")
    ),
) -> dict:
    try:
        updated = set_agent_evaluation_requirement(
            agent_id,
            payload.evaluation_required,
            payload.reason,
            principal.user_id,
        )
        identity = agent_identity_service.enroll(
            session, agent_id, updated["data"], principal
        )
        return {
            **updated,
            "agent_did": identity.did,
            "marketplace_verified": True,
        }
    except (AgentIdentityError, RegistryError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/agents/{agent_id}/telemetry")
async def agent_telemetry(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    try:
        get_definition("agents", agent_id.removeprefix("did:local:"))
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc
    return build_agent_telemetry(
        session,
        agent_id,
        limit,
        await runtime_model_pricing(),
        principal.organization_id,
    )
