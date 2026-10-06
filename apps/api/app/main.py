import logging
import shutil
import secrets
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlmodel import Session, col, select

from .agent_identity import AgentIdentityError, agent_identity_service
from .auth import Principal, require_permission
from .config import get_settings
from .database import create_db_and_tables, engine, ensure_local_identity, get_session
from .behavioral_evaluation import (
    behavioral_evaluation_readiness,
    freeze_evaluation_dataset,
    generate_evaluation_dataset,
    list_evaluation_datasets,
    shutdown_running_evaluations,
    start_behavioral_evaluation,
    update_evaluation_dataset,
)
from .evaluation import list_evaluation_runs, promote_agent, run_declaration_evaluation
from .events import event_hub
from .evidence import evidence_provider
from .github_auth import github_credentials
from .models import (
    Approval,
    EvaluationDataset,
    Event,
    Message,
    Project,
    Sandbox,
    Task,
    TaskArtifact,
    TaskStatus,
)
from .model_recovery import ModelRecoveryDecision, model_recovery_broker
from .model_catalog import list_runtime_models, runtime_model_pricing
from .mcp_gateway import mcp_gateway_app, mcp_gateway_lifespan
from .observability import (
    configure_observability,
    observability_status,
    shutdown_observability,
)
from .providers import Decision, get_governance_provider, get_sandbox_provider
from .reliability import reliability
from .repositories import (
    RepositoryError,
    get_github_repository,
    list_github_repositories,
    parse_github_url,
    validate_local_repository,
)
from .registry import RegistryError, delete_definition, get_definition, list_definitions, save_definition
from .schemas import (
    BehavioralEvaluationRunCreate,
    EvaluationDatasetCreate,
    EvaluationDatasetFreeze,
    EvaluationDatasetUpdate,
    EvaluationRunCreate,
    GitHubUrlConnect,
    ProjectCreate,
    RegistryDefinitionUpdate,
    TaskCreate,
    TaskModeUpdate,
    TaskMessageCreate,
    SessionContinuation,
    ModelRecoveryResolve,
    PublishRequest,
    SecurityEvaluationRunCreate,
    IntegrationImportRequest,
    TerminalCommand,
)
from .integrations import import_external_definition
from .security_evaluation import run_security_evaluation
from .session_service import (
    SessionServiceError,
    continue_durable_session,
    get_durable_session,
    list_durable_sessions,
)
from .telemetry import build_agent_telemetry, build_task_telemetry
from .workflow import (
    complete_approval,
    complete_publication,
    recover_interrupted_tasks,
    record_event,
    shutdown_running_tasks,
    start_task as schedule_task,
    terminate_task,
)


logger = logging.getLogger("uvicorn.error")


def _scoped_task(
    session: Session, task_id: str, principal: Principal
) -> Task | None:
    return session.exec(select(Task).where(
        Task.id == task_id, Task.organization_id == principal.organization_id
    )).first()


def _scoped_sandbox(
    session: Session, sandbox_id: str, principal: Principal
) -> Sandbox | None:
    sandbox = session.get(Sandbox, sandbox_id)
    if sandbox is None or _scoped_task(session, sandbox.task_id, principal) is None:
        return None
    return sandbox


def remove_legacy_simulation_data() -> None:
    with Session(engine) as session:
        projects = session.exec(
            select(Project).where(
                Project.repository_path == "examples/demo-repo")
        ).all()
        for project in projects:
            tasks = session.exec(select(Task).where(
                Task.project_id == project.id)).all()
            for task in tasks:
                for model in (Event, Approval, Sandbox, TaskArtifact, Message):
                    for row in session.exec(select(model).where(model.task_id == task.id)).all():
                        session.delete(row)
                session.delete(task)
            session.delete(project)
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    telemetry_enabled = configure_observability()
    logger.info(
        "OpenTelemetry export %s: %s",
        "enabled" if telemetry_enabled else "disabled",
        observability_status().get("endpoint") or "no endpoint configured",
    )
    create_db_and_tables()
    ensure_local_identity()
    if get_settings().auth_mode == "local":
        local_principal = Principal(
            get_settings().local_user_id,
            get_settings().local_organization_id,
            "admin",
        )
        with Session(engine) as session:
            for document in list_definitions("agents"):
                if document["data"].get("status") == "promoted":
                    agent_identity_service.enroll(
                        session, document["id"], document["data"], local_principal
                    )
    remove_legacy_simulation_data()
    await recover_interrupted_tasks()
    async with mcp_gateway_lifespan():
        try:
            yield
        finally:
            await shutdown_running_evaluations()
            await shutdown_running_tasks()
            shutdown_observability()


app = FastAPI(title=get_settings().app_name,
              version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/gateway", mcp_gateway_app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": get_settings().execution_mode}


@app.get("/api/gateway")
def gateway_status(
    request: Request,
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    root = str(request.base_url).rstrip("/")
    return {
        "streamable_http": f"{root}/gateway/mcp",
        "sse": f"{root}/gateway/sse",
        "messages": f"{root}/gateway/messages",
        "tools": ["sessions.list", "sessions.get", "sessions.continue"],
        "auth_mode": get_settings().auth_mode,
        "organization_id": principal.organization_id,
    }


@app.get("/api/dashboard")
def dashboard(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    tasks = session.exec(select(Task).where(
        Task.organization_id == principal.organization_id).order_by(
        col(Task.updated_at).desc())).all()
    approvals = session.exec(select(Approval).where(
        Approval.organization_id == principal.organization_id,
        Approval.status == "PENDING")).all()
    task_ids = {task.id for task in tasks}
    sandboxes = [item for item in session.exec(select(Sandbox).where(
        Sandbox.status == "READY")).all() if item.task_id in task_ids]
    inactive = {TaskStatus.DONE, TaskStatus.CANCELLED,
                TaskStatus.FAILED, TaskStatus.DRAFT}
    return {
        "metrics": {
            "active_tasks": sum(t.status not in inactive for t in tasks),
            "awaiting_approval": len(approvals),
            "running_agents": sum(
                t.status not in inactive | {TaskStatus.AWAITING_APPROVAL} for t in tasks
            ),
            "security_findings": 1 if any(
                t.status in {TaskStatus.SECURITY, TaskStatus.REVIEW,
                             TaskStatus.AWAITING_APPROVAL, TaskStatus.DONE}
                for t in tasks
            ) else 0,
            "sandboxes_ready": len(sandboxes),
        },
        "tasks": tasks,
    }


@app.get("/api/projects", response_model=list[Project])
def list_projects(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return session.exec(select(Project).where(
        Project.organization_id == principal.organization_id).order_by(Project.name)).all()


@app.post("/api/projects", response_model=Project, status_code=201)
def create_project(
    payload: ProjectCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("project.create")),
):
    if payload.source_type == "local":
        try:
            resolved = validate_local_repository(payload.repository_path)
        except RepositoryError as exc:
            raise HTTPException(422, str(exc)) from exc
        payload.repository_path = str(resolved)
    else:
        if not payload.repository_url:
            raise HTTPException(422, "A GitHub clone URL is required")
        try:
            parse_github_url(payload.repository_url)
        except RepositoryError as exc:
            raise HTTPException(422, str(exc)) from exc
    project = Project.model_validate(payload, update={
        "organization_id": principal.organization_id,
        "created_by": principal.user_id,
    })
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@app.get("/api/tasks", response_model=list[Task])
def list_tasks(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return session.exec(select(Task).where(
        Task.organization_id == principal.organization_id).order_by(
        col(Task.created_at).desc())).all()


@app.post("/api/tasks", response_model=Task, status_code=201)
async def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.create")),
):
    project = session.exec(select(Project).where(
        Project.id == payload.project_id,
        Project.organization_id == principal.organization_id,
    )).first()
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        agent = get_definition(
            "agents", payload.agent_id.removeprefix("did:local:"))["data"]
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc
    if agent.get("status") != "promoted":
        raise HTTPException(409, "Only promoted agent versions can run tasks")
    try:
        identity = agent_identity_service.enroll(
            session,
            payload.agent_id.removeprefix("did:local:"),
            agent,
            principal,
        )
        agent_identity_service.verify(
            session,
            payload.agent_id.removeprefix("did:local:"),
            principal.organization_id,
            agent,
        )
    except AgentIdentityError as exc:
        raise HTTPException(409, str(exc)) from exc
    existing_ids = session.exec(select(Task.id)).all()
    numeric_ids = (
        int(value.removeprefix("TASK-"))
        for value in existing_ids
        if value.startswith("TASK-") and value.removeprefix("TASK-").isdigit()
    )
    next_id = max(numeric_ids, default=0) + 1
    task = Task(
        id=f"TASK-{next_id:03d}", **payload.model_dump(),
        organization_id=principal.organization_id, created_by=principal.user_id,
    )
    task.branch = f"feature/{task.id.lower()}"
    session.add(task)
    session.commit()
    session.refresh(task)
    await record_event(session, task.id, "task.created", "Task created", task.title)
    await record_event(
        session,
        task.id,
        "agent.identity_verified",
        "AgentMesh identity verified",
        identity.did,
        data={"agent_did": identity.did,
              "organization_id": principal.organization_id},
    )
    evidence_provider.write(task.id, "task", task.model_dump(mode="json"))
    return task


@app.get("/api/tasks/{task_id}")
def get_task(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    task = session.exec(select(Task).where(
        Task.id == task_id, Task.organization_id == principal.organization_id
    )).first()
    if not task:
        raise HTTPException(404, "Task not found")
    project = session.get(Project, task.project_id)
    events = session.exec(
        select(Event).where(Event.task_id ==
                            task_id).order_by(Event.created_at)
    ).all()
    artifacts = session.exec(select(TaskArtifact).where(
        TaskArtifact.task_id == task_id)).all()
    sandbox = session.exec(select(Sandbox).where(
        Sandbox.task_id == task_id)).first()
    approval = session.exec(select(Approval).where(
        Approval.task_id == task_id, Approval.status == "PENDING"
    )).first()
    messages = session.exec(
        select(Message).where(Message.task_id ==
                              task_id).order_by(Message.created_at)
    ).all()
    return {
        "task": task, "project": project, "events": events,
        "artifacts": {item.kind: item.content for item in artifacts},
        "sandbox": sandbox, "approval": approval, "messages": messages,
        "model_recovery": model_recovery_broker.get(task_id),
    }


@app.get("/api/tasks/{task_id}/observability")
async def task_observability(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    task = _scoped_task(session, task_id, principal)
    if task is None:
        raise HTTPException(404, "Task not found")
    report = build_task_telemetry(session, task_id, await runtime_model_pricing())
    if report is None:
        raise HTTPException(404, "Task not found")
    return report


@app.get("/api/reliability")
def reliability_status(
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    return reliability.status()


@app.post("/api/tasks/{task_id}/model-recovery")
async def resolve_model_recovery(
    task_id: str,
    payload: ModelRecoveryResolve,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> dict:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.AWAITING_MODEL:
        raise HTTPException(
            409, "Task is not waiting for a model recovery decision")
    decision = ModelRecoveryDecision(payload.action, payload.model)
    if not model_recovery_broker.resolve(task_id, decision):
        raise HTTPException(409, "Model recovery request is no longer active")
    return {"status": "accepted", "action": payload.action, "model": payload.model}


@app.post("/api/tasks/{task_id}/run", status_code=202)
async def start_task(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> dict:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in {TaskStatus.DRAFT, TaskStatus.FAILED}:
        raise HTTPException(409, f"Task cannot run from {task.status}")
    schedule_task(task_id)
    return {"status": "started", "task_id": task_id}


@app.patch("/api/tasks/{task_id}/mode", response_model=Task)
def update_task_mode(
    task_id: str,
    payload: TaskModeUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> Task:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in {TaskStatus.DRAFT, TaskStatus.FAILED}:
        raise HTTPException(
            409, "Task mode can only change before a run or retry")
    task.mode = payload.mode
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> Task:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    await terminate_task(task_id)
    task.status = TaskStatus.CANCELLED
    task.phase = "Cancelled"
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    await record_event(
        session, task_id, "agent.completed", "Agent terminated",
        "User activated kill switch", "warning",
    )
    return task


@app.get("/api/approvals", response_model=list[Approval])
def approvals(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return session.exec(select(Approval).where(
        Approval.organization_id == principal.organization_id
    ).order_by(col(Approval.created_at).desc())).all()


@app.get("/api/governance")
def governance_overview(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    approvals = session.exec(
        select(Approval).where(
            Approval.organization_id == principal.organization_id
        ).order_by(col(Approval.created_at).desc())
    ).all()
    task_ids = set(session.exec(select(Task.id).where(
        Task.organization_id == principal.organization_id
    )).all())
    decisions = session.exec(
        select(Event).where(
            Event.type.in_(["tool.allowed", "tool.denied"])
        ).order_by(col(Event.created_at).desc()).limit(200)
    ).all()
    decisions = [item for item in decisions if item.task_id in task_ids]
    return {
        "approvals": approvals,
        "decisions": decisions,
        "summary": {
            "pending_approvals": sum(item.status == "PENDING" for item in approvals),
            "allowed": sum(item.type == "tool.allowed" for item in decisions),
            "denied": sum(item.type == "tool.denied" for item in decisions),
        },
    }


@app.post("/api/approvals/{approval_id}/approve")
async def approve(
    approval_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("approval.decide")),
) -> Approval:
    approval = session.get(Approval, approval_id)
    if (
        not approval
        or approval.organization_id != principal.organization_id
        or approval.status != "PENDING"
    ):
        raise HTTPException(404, "Pending approval not found")
    if (
        get_settings().auth_mode != "local"
        and approval.requester_id == principal.user_id
    ):
        raise HTTPException(403, "Requesters cannot approve their own action")
    approval.status = "APPROVED"
    approval.approver_id = principal.user_id
    approval.decided_at = datetime.now(UTC)
    session.add(approval)
    session.commit()
    await record_event(
        session, approval.task_id, "approval.approved", "Approval granted", approval.action
    )
    if approval.action == "git.commit":
        await complete_approval(approval.task_id)
    elif approval.action == "repository.publish":
        await complete_publication(
            approval.task_id,
            str(approval.scope["branch"]),
            bool(approval.scope.get("create_pull_request")),
        )
    else:
        raise HTTPException(
            409, f"Unsupported approval action: {approval.action}")
    return approval


@app.post("/api/approvals/{approval_id}/deny")
async def deny(
    approval_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("approval.decide")),
) -> Approval:
    approval = session.get(Approval, approval_id)
    if (
        not approval
        or approval.organization_id != principal.organization_id
        or approval.status != "PENDING"
    ):
        raise HTTPException(404, "Pending approval not found")
    approval.status = "DENIED"
    approval.approver_id = principal.user_id
    approval.decided_at = datetime.now(UTC)
    task = session.get(Task, approval.task_id)
    if task and approval.action == "git.commit":
        task.status = TaskStatus.IMPLEMENTATION
        task.phase = "Implementation"
        task.progress = 48
        session.add(task)
    session.add(approval)
    session.commit()
    await record_event(
        session, approval.task_id, "approval.denied", "Approval denied", approval.action, "warning"
    )
    return approval


@app.post("/api/tasks/{task_id}/publish", status_code=202)
async def request_publication(
    task_id: str,
    payload: PublishRequest,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> dict:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.DONE:
        raise HTTPException(409, "Only completed tasks can be published")
    actions = ["git.push"]
    if payload.create_pull_request:
        actions.append("pull_request.create")
    decisions = [
        await get_governance_provider().evaluate(
            task.agent_id,
            action,
            {"branch": payload.branch},
            {"task_id": task_id, "organization_id": principal.organization_id},
        )
        for action in actions
    ]
    denied = next(
        (item for item in decisions if item.decision == Decision.DENY), None)
    if denied:
        raise HTTPException(403, denied.reason)
    approval_id = f"APR-PUBLISH-{task_id.removeprefix('TASK-')}"
    approval = session.get(Approval, approval_id) or Approval(
        id=approval_id,
        task_id=task_id,
        action="repository.publish",
        organization_id=task.organization_id,
        requester_id=principal.user_id,
    )
    approval.status = "PENDING"
    approval.scope = {
        "branch": payload.branch,
        "create_pull_request": payload.create_pull_request,
        "actions": actions,
    }
    approval.reason = "Publishing requires explicit scoped approval"
    session.add(approval)
    session.commit()
    await record_event(
        session,
        task_id,
        "approval.created",
        "Publication approval requested",
        ", ".join(actions),
        "warning",
        {"branch": payload.branch},
    )
    return {"status": "awaiting_approval", "approval_id": approval.id, "actions": actions}


@app.post("/api/sandboxes/{sandbox_id}/execute")
async def terminal(
    sandbox_id: str,
    payload: TerminalCommand,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("sandbox.operate")),
) -> dict:
    sandbox = _scoped_sandbox(session, sandbox_id, principal)
    if not sandbox or sandbox.status != "READY":
        raise HTTPException(404, "Ready sandbox not found")
    if not sandbox.container_id:
        raise HTTPException(409, "Sandbox has no Docker container")
    return await get_sandbox_provider().execute(sandbox.container_id, payload.command)


@app.get("/api/sandboxes", response_model=list[Sandbox])
def list_sandboxes(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> list[Sandbox]:
    task_ids = set(session.exec(select(Task.id).where(
        Task.organization_id == principal.organization_id
    )).all())
    return [item for item in session.exec(
        select(Sandbox).order_by(col(Sandbox.created_at).desc())
    ).all() if item.task_id in task_ids]


@app.post("/api/sandboxes/{sandbox_id}/kill")
async def kill_sandbox(
    sandbox_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("sandbox.operate")),
) -> Sandbox:
    sandbox = _scoped_sandbox(session, sandbox_id, principal)
    if not sandbox:
        raise HTTPException(404, "Sandbox not found")
    if sandbox.container_id:
        await get_sandbox_provider().kill(sandbox.container_id)
    sandbox.status = "KILLED"
    session.add(sandbox)
    session.commit()
    await record_event(
        session, sandbox.task_id, "sandbox.killed", "Sandbox killed",
        "Evidence was preserved", "warning",
    )
    return sandbox


@app.get("/api/tasks/{task_id}/evidence")
def evidence(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    if not _scoped_task(session, task_id, principal):
        raise HTTPException(404, "Task not found")
    return evidence_provider.bundle(task_id)


@app.get("/api/evidence")
def evidence_overview(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> list[dict]:
    tasks = session.exec(select(Task).where(
        Task.organization_id == principal.organization_id).order_by(
        col(Task.updated_at).desc())).all()
    task_ids = {task.id for task in tasks}
    artifacts = [item for item in session.exec(select(TaskArtifact)).all()
                 if item.task_id in task_ids]
    kinds_by_task: dict[str, list[str]] = {}
    for artifact in artifacts:
        kinds_by_task.setdefault(artifact.task_id, []).append(artifact.kind)
    return [{
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "updated_at": task.updated_at,
        "artifact_kinds": sorted(kinds_by_task.get(task.id, [])),
    } for task in tasks]


@app.get("/api/security")
def security_overview(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    artifacts = session.exec(
        select(TaskArtifact).where(TaskArtifact.kind == "security").order_by(
            col(TaskArtifact.created_at).desc()
        )
    ).all()
    tasks = {task.id: task for task in session.exec(select(Task).where(
        Task.organization_id == principal.organization_id)).all()}
    artifacts = [item for item in artifacts if item.task_id in tasks]
    findings = [{
        "task_id": artifact.task_id,
        "title": tasks[artifact.task_id].title if artifact.task_id in tasks else artifact.task_id,
        "status": tasks[artifact.task_id].status if artifact.task_id in tasks else "UNKNOWN",
        "created_at": artifact.created_at,
        **artifact.content,
    } for artifact in artifacts]
    return {
        "summary": {
            severity: sum(int(item.get(severity, 0)) for item in findings)
            for severity in ("high", "medium", "low")
        },
        "findings": findings,
    }


@app.get("/api/doctor")
def doctor() -> dict:
    tools = ["docker", "copilot", "ollama",
             "semgrep", "trivy", "gitleaks", "git", "node"]
    return {
        "mode": get_settings().execution_mode,
        "agent_framework": {
            "available": True,
            "providers": ["github-copilot", "ollama"],
        },
        "checks": [{"name": tool, "available": shutil.which(tool) is not None} for tool in tools],
    }


@app.get("/api/connectors/github/repos")
async def github_repositories(
    owner: str, principal: Principal = Depends(require_permission("read"))
) -> dict:
    try:
        repositories = await list_github_repositories(owner)
    except (RepositoryError, httpx.HTTPError) as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"owner": owner, "repositories": repositories, "authenticated": bool(github_credentials.token)}


@app.post("/api/connectors/github/repo")
async def github_repository(
    payload: GitHubUrlConnect,
    principal: Principal = Depends(require_permission("project.create")),
) -> dict:
    try:
        return await get_github_repository(payload.url)
    except RepositoryError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "GitHub could not be reached") from exc


@app.get("/api/connectors/github/oauth/start")
def start_github_oauth(
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    settings = get_settings()
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise HTTPException(503, "GitHub OAuth is not configured")
    state = github_credentials.create_state()
    query = urlencode({
        "client_id": settings.github_oauth_client_id,
        "scope": settings.github_oauth_scope,
        "state": state,
        "allow_signup": "true",
    })
    response = RedirectResponse(
        f"https://github.com/login/oauth/authorize?{query}")
    response.set_cookie(
        "workbench_github_oauth_state", state, max_age=600, httponly=True,
        secure=False, samesite="lax", path="/api/connectors/github/oauth",
    )
    return response


@app.get("/api/connectors/github/oauth/callback")
async def github_oauth_callback(request: Request, code: str, state: str) -> RedirectResponse:
    cookie_state = request.cookies.get("workbench_github_oauth_state")
    if (
        not cookie_state
        or not secrets.compare_digest(cookie_state, state)
        or not github_credentials.consume_state(state)
    ):
        raise HTTPException(400, "GitHub OAuth state is invalid or expired")
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "state": state,
            },
        )
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not token:
            raise HTTPException(400, "GitHub did not issue an access token")
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        user_response.raise_for_status()
    github_credentials.connect(user_response.json()["login"], token)
    response = RedirectResponse(
        f"{settings.web_app_url.rstrip('/')}?github=connected", status_code=303)
    response.delete_cookie("workbench_github_oauth_state",
                           path="/api/connectors/github/oauth")
    return response


@app.post("/api/connectors/github/disconnect")
def disconnect_github(
    principal: Principal = Depends(require_permission("project.create")),
) -> dict:
    github_credentials.disconnect()
    return {
        "authenticated": bool(github_credentials.token),
        "method": github_credentials.method,
    }


@app.get("/api/runtime")
async def runtime_status(
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    model_error = None
    try:
        models = await list_runtime_models()
    except RuntimeError as exc:
        models = []
        model_error = str(exc)
    settings = get_settings()
    sandbox = await get_sandbox_provider().readiness()
    requested_provider = settings.model_provider
    active_provider = str(models[0].get(
        "provider") or requested_provider) if models else requested_provider
    fallback_active = any(bool(item.get("fallback")) for item in models)
    return {
        "mode": settings.execution_mode,
        "model_provider": requested_provider,
        "active_model_provider": active_provider,
        "model_fallback_active": fallback_active,
        "configured_model": settings.model_name,
        "model_request_timeout_seconds": settings.model_request_timeout_seconds,
        "agent_turn_timeout_seconds": settings.agent_turn_timeout_seconds,
        "model_recovery_timeout_seconds": settings.model_recovery_timeout_seconds,
        "sandbox_command_timeout_seconds": settings.sandbox_command_timeout_seconds,
        "ollama_reachable": any(item.get("provider") == "ollama" for item in models),
        "models": [
            {
                "name": item.get("name"), "size": item.get("size"),
                "provider": item.get("provider") or requested_provider,
                "fallback": bool(item.get("fallback")),
            }
            for item in models
        ],
        "model_available": bool(models),
        "model_error": model_error,
        "sandbox_provider": settings.sandbox_provider,
        "sandbox_available": sandbox["ready"],
        "sandbox": sandbox,
        "docker_available": sandbox["ready"] if settings.sandbox_provider == "docker" else False,
        "docker": sandbox if settings.sandbox_provider == "docker" else None,
        "github_authenticated": bool(github_credentials.token),
        "github_login": github_credentials.login,
        "github_auth_method": github_credentials.method,
        "github_oauth_configured": bool(
            get_settings().github_oauth_client_id
            and get_settings().github_oauth_client_secret
        ),
        "observability": observability_status(),
    }


@app.post("/api/tasks/{task_id}/messages", response_model=Message, status_code=201)
async def send_message(
    task_id: str,
    payload: TaskMessageCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> Message:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in {
        TaskStatus.INTAKE, TaskStatus.PLANNING, TaskStatus.IMPLEMENTATION
    }:
        raise HTTPException(
            409,
            "Steering is available only while the coding agent is active. Start or retry the task first.",
        )
    message = Message(task_id=task_id, role="user", content=payload.content)
    session.add(message)
    session.commit()
    session.refresh(message)
    await record_event(session, task_id, "developer.message", "Developer steering", payload.content)
    session.refresh(message)
    return message


@app.get("/api/sessions")
def list_sessions(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> list[dict]:
    return list_durable_sessions(session, principal)


@app.get("/api/sessions/{task_id}")
def session_history(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    try:
        return get_durable_session(session, task_id, principal)
    except SessionServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@app.post("/api/sessions/{task_id}/messages", status_code=202)
async def continue_session(
    task_id: str,
    payload: SessionContinuation,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> dict:
    try:
        return await continue_durable_session(
            session, task_id, payload.content, payload.agent_id, principal
        )
    except SessionServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@app.post("/api/tasks/{task_id}/open")
def open_task_workspace(
    task_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("task.operate")),
) -> dict:
    if not _scoped_task(session, task_id, principal):
        raise HTTPException(404, "Task not found")
    sandbox = session.exec(select(Sandbox).where(
        Sandbox.task_id == task_id)).first()
    if not sandbox or not sandbox.host_workspace:
        raise HTTPException(404, "Task worktree is not available yet")
    if get_settings().web_editor_url:
        editor_url = get_settings().web_editor_url.replace(
            "{workspace}", quote(sandbox.host_workspace, safe="/")
        )
        return {"opened": False, "url": editor_url, "workspace": sandbox.host_workspace}
    code = shutil.which("code")
    if not code:
        raise HTTPException(
            503, "VS Code CLI is not available to the control plane")
    subprocess.Popen([code, "-r", sandbox.host_workspace],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"opened": True, "workspace": sandbox.host_workspace}


@app.get("/api/registry/{kind}")
def registry_list(
    kind: str, principal: Principal = Depends(require_permission("read"))
) -> list[dict]:
    try:
        return list_definitions(kind)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/integrations/import", status_code=201)
async def import_integration(
    payload: IntegrationImportRequest,
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    try:
        return await import_external_definition(
            payload.url, kind=payload.kind, identifier=payload.identifier
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            502, "Integration source could not be fetched") from exc


@app.get("/api/marketplace/agents")
def marketplace_agents(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> list[dict]:
    return agent_identity_service.list_entries(session, principal.organization_id)


@app.post("/api/marketplace/agents/{agent_id}/revoke")
def revoke_marketplace_agent(
    agent_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    try:
        record = agent_identity_service.revoke(
            session, agent_id, principal.organization_id
        )
    except AgentIdentityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"agent_id": agent_id, "agent_did": record.did, "status": record.status}


@app.get("/api/registry/{kind}/{identifier}")
def registry_get(
    kind: str,
    identifier: str,
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    try:
        return get_definition(kind, identifier)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/registry/{kind}/{identifier}")
def registry_put(
    kind: str,
    identifier: str,
    payload: RegistryDefinitionUpdate,
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    try:
        return save_definition(kind, identifier, payload.raw)
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/registry/{kind}/{identifier}", status_code=204)
def registry_delete(
    kind: str,
    identifier: str,
    principal: Principal = Depends(require_permission("registry.manage")),
) -> None:
    try:
        delete_definition(kind, identifier)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/evaluations")
def evaluations(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return list_evaluation_runs(session, principal.organization_id)


@app.post("/api/evaluations/run", status_code=201, include_in_schema=False)
@app.post("/api/evaluations/declaration", status_code=201)
def run_declaration_check(
    payload: EvaluationRunCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    try:
        return run_declaration_evaluation(
            session, payload.agent_id, payload.suite_id,
            principal.organization_id, principal.user_id,
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/evaluations/security", status_code=201)
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


@app.get("/api/evaluation-datasets", response_model=list[EvaluationDataset])
def evaluation_datasets(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    return list_evaluation_datasets(session, principal.organization_id)


@app.get("/api/evaluations/behavioral/readiness")
async def behavioral_readiness(
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    return await behavioral_evaluation_readiness()


@app.get("/api/evaluation-datasets/{dataset_id}", response_model=EvaluationDataset)
def evaluation_dataset(
    dataset_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
):
    dataset = session.get(EvaluationDataset, dataset_id)
    if not dataset or dataset.organization_id != principal.organization_id:
        raise HTTPException(404, "Evaluation dataset not found")
    return dataset


@app.post("/api/evaluation-datasets", response_model=EvaluationDataset, status_code=201)
def create_evaluation_dataset(
    payload: EvaluationDatasetCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("evaluation.manage")),
):
    try:
        agent = get_definition("agents", payload.agent_id)["data"]
        agent_identity_service.enroll(
            session, payload.agent_id, agent, principal)
        return generate_evaluation_dataset(
            session, payload.agent_id, payload.suite_id, payload.generation_model,
            principal.organization_id, principal.user_id,
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/evaluation-datasets/{dataset_id}", response_model=EvaluationDataset)
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
            session, dataset_id, payload.scenarios, payload.reviewed_by
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/evaluation-datasets/{dataset_id}/freeze", response_model=EvaluationDataset)
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
        return freeze_evaluation_dataset(session, dataset_id, payload.reviewed_by)
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/evaluations/behavioral", status_code=202)
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
            session, payload.dataset_id, payload.model_name, payload.adapters
        )
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/agents/{agent_id}/promote")
def promote(
    agent_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    try:
        promoted = promote_agent(session, agent_id, principal.organization_id)
        identity = agent_identity_service.enroll(
            session, agent_id, promoted["data"], principal
        )
        return {**promoted, "agent_did": identity.did, "marketplace_verified": True}
    except RegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/agents/{agent_id}/telemetry")
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
        session, agent_id, limit, await runtime_model_pricing(),
        principal.organization_id,
    )


@app.websocket("/api/events/ws")
async def events_socket(
    websocket: WebSocket,
    principal: Principal = Depends(require_permission("read")),
):
    await event_hub.connect(websocket, principal.organization_id)
    try:
        await websocket.send_json({"event": "connected"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_hub.disconnect(websocket)


@app.websocket("/api/tasks/{task_id}/events/ws")
async def task_events_socket(
    websocket: WebSocket,
    task_id: str,
    principal: Principal = Depends(require_permission("read")),
):
    with Session(engine) as session:
        if not _scoped_task(session, task_id, principal):
            await websocket.close(code=4404, reason="Task not found")
            return
    await event_hub.connect(websocket, principal.organization_id, task_id)
    try:
        await websocket.send_json({"event": "connected", "task_id": task_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_hub.disconnect(websocket)
