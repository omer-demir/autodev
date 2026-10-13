import base64
import html
import hashlib
import json
import logging
import shutil
import secrets
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import delete, func, or_
from sqlmodel import Session, col, select

from .agent_identity import AgentIdentityError, agent_identity_service
from .auth import (
    OIDCAuthenticator,
    Principal,
    create_browser_session,
    current_principal,
    delete_browser_session,
    provision_oidc_principal,
    require_permission,
)
from .config import get_settings
from .database import create_db_and_tables, engine, ensure_local_identity, get_session
from .behavioral_evaluation import (
    ensure_evaluation_baselines,
    shutdown_running_evaluations,
)
from .events import event_hub
from .evidence import evidence_provider
from .execution_queue import ExecutionConflict
from .github_auth import github_credentials
from .models import (
    Approval,
    Connector,
    EvaluationRun,
    Event,
    ExecutionJob,
    Message,
    Membership,
    Project,
    Sandbox,
    Task,
    TaskArtifact,
    TaskStatus,
    User,
    WorkspaceRevision,
)
from .model_recovery import ModelRecoveryDecision, model_recovery_broker
from .model_catalog import list_runtime_models, runtime_model_pricing
from .mcp_gateway import mcp_gateway_app, mcp_gateway_lifespan
from .observability import (
    configure_logging,
    configure_observability,
    observe_http_request,
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
    remove_task_workspace,
    validate_local_repository,
    validate_publication,
)
from .routers import evaluations_router, registry_router
from .registry import (
    RegistryError,
    agent_can_execute,
    get_definition,
    list_definitions,
)
from .schemas import (
    GitHubUrlConnect,
    ProjectCreate,
    RuntimeElevationRequest,
    TaskCreate,
    TaskModeUpdate,
    TaskMessageCreate,
    SessionContinuation,
    ModelRecoveryResolve,
    PublishRequest,
    MembershipCreate,
    MembershipRoleUpdate,
    TerminalCommand,
)
from .session_service import (
    SessionServiceError,
    continue_durable_session,
    get_durable_session,
    list_durable_sessions,
)
from .telemetry import build_task_telemetry
from .workflow import (
    complete_approval,
    complete_publication,
    recover_interrupted_tasks,
    record_event,
    request_runtime_elevation,
    shutdown_running_tasks,
    start_task as schedule_task,
    terminate_task,
)
from .workflow_orchestration import workflow_owner_agent
from .workspace_snapshots import workspace_snapshots


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


def _connector_payload(connector: Connector) -> dict:
    return {
        "id": connector.id,
        "provider": connector.provider,
        "name": connector.name,
        "auth_method": connector.auth_method,
        "status": connector.status,
        "account_login": connector.account_login,
        "metadata": connector.metadata_,
        "created_by": connector.created_by,
        "created_at": connector.created_at,
        "updated_at": connector.updated_at,
    }


def _github_manifest_app_name(display_name: str, connector_id: str) -> str:
    prefix = "".join(
        character for character in display_name if character.isalnum())
    return f"{(prefix[:20] or 'AutoDev')}-{connector_id[-12:].lower()}"


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
    configure_logging()
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
                if agent_can_execute(document["data"]):
                    agent_identity_service.enroll(
                        session, document["id"], document["data"], local_principal
                    )
            baselines = ensure_evaluation_baselines(
                session, local_principal.organization_id, local_principal.user_id
            )
            logger.info(
                "Ensured %d baseline evaluation datasets for organization %s",
                len(baselines), local_principal.organization_id,
            )
    remove_legacy_simulation_data()
    if get_settings().execution_dispatch == "embedded":
        await recover_interrupted_tasks()
    async with mcp_gateway_lifespan():
        try:
            yield
        finally:
            await shutdown_running_evaluations()
            if get_settings().execution_dispatch == "embedded":
                await shutdown_running_tasks()
            await event_hub.close()
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


@app.middleware("http")
async def observe_http_metrics(request: Request, call_next):
    started = time.monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "unmatched")
        observe_http_request(
            method=request.method,
            route=route,
            status_code=status_code,
            duration_seconds=time.monotonic() - started,
        )


app.mount("/gateway", mcp_gateway_app)
app.include_router(registry_router)
app.include_router(evaluations_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": get_settings().execution_mode}


def _require_oidc_login_settings() -> None:
    settings = get_settings()
    required = {
        "authorization URL": settings.oidc_authorization_url,
        "token URL": settings.oidc_token_url,
        "client ID": settings.oidc_client_id,
        "client secret": settings.oidc_client_secret,
        "redirect URI": settings.oidc_redirect_uri,
    }
    missing = [name for name, value in required.items() if not value]
    if settings.auth_mode != "oidc" or missing:
        detail = ", ".join(missing) if missing else "OIDC auth mode"
        raise HTTPException(
            503, f"OIDC browser login is not configured: {detail}")


@app.get("/api/auth/login")
def oidc_login() -> RedirectResponse:
    _require_oidc_login_settings()
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    query = urlencode({
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    response = RedirectResponse(f"{settings.oidc_authorization_url}?{query}")
    for name, value in (
        ("workbench_oidc_state", state),
        ("workbench_oidc_nonce", nonce),
        ("workbench_oidc_verifier", verifier),
    ):
        response.set_cookie(
            name, value, max_age=600, httponly=True,
            secure=settings.session_cookie_secure, samesite="lax",
            path="/api/auth/callback",
        )
    return response


@app.get("/api/auth/callback")
async def oidc_callback(
    request: Request,
    code: str,
    state: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    _require_oidc_login_settings()
    settings = get_settings()
    cookie_state = request.cookies.get("workbench_oidc_state")
    verifier = request.cookies.get("workbench_oidc_verifier")
    nonce = request.cookies.get("workbench_oidc_nonce")
    if not cookie_state or not verifier or not nonce or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(400, "OIDC login state is invalid or expired")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post(
                str(settings.oidc_token_url),
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                    "redirect_uri": settings.oidc_redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                },
            )
            token_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "OIDC token exchange failed") from exc
    id_token = token_response.json().get("id_token")
    if not id_token:
        raise HTTPException(400, "OIDC provider did not issue an ID token")
    try:
        claims = OIDCAuthenticator(settings).decode(str(id_token))
    except Exception as exc:
        raise HTTPException(401, "OIDC ID token is invalid") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise HTTPException(401, "OIDC ID token nonce is invalid")
    principal = provision_oidc_principal(session, claims, settings, None)
    token, _ = create_browser_session(session, principal, settings)
    response = RedirectResponse(settings.web_app_url)
    response.set_cookie(
        "workbench_session", token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True, secure=settings.session_cookie_secure,
        samesite="lax", path="/",
    )
    for name in ("workbench_oidc_state", "workbench_oidc_nonce", "workbench_oidc_verifier"):
        response.delete_cookie(name, path="/api/auth/callback")
    return response


@app.get("/api/auth/me")
def auth_me(principal: Principal = Depends(current_principal)) -> dict:
    return {
        "user_id": principal.user_id,
        "organization_id": principal.organization_id,
        "role": principal.role,
        "email": principal.email,
        "auth_mode": get_settings().auth_mode,
    }


@app.post("/api/auth/logout", status_code=204)
def auth_logout(
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    delete_browser_session(session, request.cookies.get("workbench_session"))
    response = Response(status_code=204)
    response.delete_cookie("workbench_session", path="/")
    return response


def _member_payload(membership: Membership, user: User | None) -> dict:
    return {
        "user_id": membership.user_id,
        "email": user.email if user else None,
        "display_name": user.display_name if user else None,
        "role": membership.role,
        "created_at": membership.created_at,
    }


@app.get("/api/admin/members")
def list_members(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("membership.manage")),
) -> list[dict]:
    memberships = session.exec(select(Membership).where(
        Membership.organization_id == principal.organization_id
    ).order_by(Membership.role, Membership.user_id)).all()
    return [_member_payload(item, session.get(User, item.user_id)) for item in memberships]


@app.post("/api/admin/members", status_code=201)
def create_member(
    payload: MembershipCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("membership.manage")),
) -> dict:
    if session.get(Membership, (payload.user_id, principal.organization_id)):
        raise HTTPException(409, "Membership already exists")
    user = session.get(User, payload.user_id)
    if user is None:
        user = User(
            id=payload.user_id,
            email=payload.email,
            display_name=payload.display_name,
            issuer="provisioned",
        )
        session.add(user)
    membership = Membership(
        user_id=payload.user_id,
        organization_id=principal.organization_id,
        role=payload.role,
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return _member_payload(membership, user)


@app.patch("/api/admin/members/{user_id}")
def update_member(
    user_id: str,
    payload: MembershipRoleUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("membership.manage")),
) -> dict:
    membership = session.get(Membership, (user_id, principal.organization_id))
    if membership is None:
        raise HTTPException(404, "Membership not found")
    if user_id == principal.user_id and payload.role != "admin":
        raise HTTPException(409, "You cannot remove your own admin role")
    membership.role = payload.role
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return _member_payload(membership, session.get(User, user_id))


@app.delete("/api/admin/members/{user_id}", status_code=204)
def delete_member(
    user_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("membership.manage")),
) -> None:
    membership = session.get(Membership, (user_id, principal.organization_id))
    if membership is None:
        raise HTTPException(404, "Membership not found")
    if user_id == principal.user_id:
        raise HTTPException(409, "You cannot remove your own membership")
    session.delete(membership)
    session.commit()


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
    task_scope = Task.organization_id == principal.organization_id
    tasks = session.exec(select(Task).where(
        task_scope).order_by(col(Task.updated_at).desc()).limit(5)).all()
    all_tasks = session.exec(select(Task).where(
        Task.organization_id == principal.organization_id).order_by(
        col(Task.updated_at).desc())).all()
    approvals = session.exec(select(Approval).where(
        Approval.organization_id == principal.organization_id,
        Approval.status == "PENDING")).all()
    task_ids = {task.id for task in all_tasks}
    sandboxes = [item for item in session.exec(select(Sandbox).where(
        Sandbox.status == "READY")).all() if item.task_id in task_ids]
    inactive = {TaskStatus.DONE, TaskStatus.CANCELLED,
                TaskStatus.FAILED, TaskStatus.DRAFT}
    return {
        "metrics": {
            "active_tasks": sum(t.status not in inactive for t in all_tasks),
            "awaiting_approval": len(approvals),
            "running_agents": sum(
                t.status not in inactive | {TaskStatus.AWAITING_APPROVAL} for t in all_tasks
            ),
            "security_findings": 1 if any(
                t.status in {TaskStatus.SECURITY, TaskStatus.REVIEW,
                             TaskStatus.AWAITING_APPROVAL, TaskStatus.DONE}
                for t in all_tasks
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
        if not payload.repository_path:
            raise HTTPException(422, "A local Git repository path is required")
        try:
            resolved = validate_local_repository(payload.repository_path)
        except RepositoryError as exc:
            raise HTTPException(422, str(exc)) from exc
        payload.repository_path = str(resolved)
    elif payload.source_type == "github":
        if not payload.repository_url:
            raise HTTPException(422, "A GitHub clone URL is required")
        try:
            parse_github_url(payload.repository_url)
        except RepositoryError as exc:
            raise HTTPException(422, str(exc)) from exc
        if payload.connector_id:
            connector = github_credentials.get_connector(
                payload.connector_id, principal.organization_id
            )
            if not connector or connector.provider != "github":
                raise HTTPException(
                    422, "The selected GitHub connection is unavailable")
            if connector.status != "ACTIVE":
                raise HTTPException(
                    409, "Install the selected GitHub connection first")
            owner, _ = parse_github_url(payload.repository_url)
            if not github_credentials.get_installation(
                principal.organization_id,
                None,
                owner,
                payload.connector_id,
            ):
                raise HTTPException(
                    422,
                    "The selected connection is not installed for this repository owner",
                )
    project = Project.model_validate(payload, update={
        "organization_id": principal.organization_id,
        "created_by": principal.user_id,
    })
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@app.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("project.delete")),
) -> Response:
    project = session.exec(select(Project).where(
        Project.id == project_id,
        Project.organization_id == principal.organization_id,
    )).first()
    if not project:
        raise HTTPException(404, "Project not found")

    tasks = session.exec(select(Task).where(
        Task.project_id == project_id,
        Task.organization_id == principal.organization_id,
    )).all()
    task_ids = [task.id for task in tasks]
    inactive = {
        TaskStatus.DRAFT,
        TaskStatus.AWAITING_APPROVAL,
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
    active_tasks = [task.id for task in tasks if task.status not in inactive]
    if task_ids:
        active_jobs = session.exec(select(ExecutionJob.task_id).where(
            col(ExecutionJob.task_id).in_(task_ids),
            col(ExecutionJob.status).in_({"QUEUED", "RUNNING"}),
        )).all()
        active_tasks = sorted(set(active_tasks) | set(active_jobs))
    if active_tasks:
        raise HTTPException(
            409,
            "Cancel active tasks before removing this repository: "
            + ", ".join(active_tasks),
        )

    for task_id in task_ids:
        await terminate_task(task_id)
        evidence_provider.delete_task(task_id)
        workspace_snapshots.delete_task(task_id)
        remove_task_workspace(task_id)

    if task_ids:
        for model in (
            Approval,
            Event,
            ExecutionJob,
            Message,
            Sandbox,
            TaskArtifact,
            WorkspaceRevision,
        ):
            session.exec(delete(model).where(col(model.task_id).in_(task_ids)))
        session.exec(delete(Task).where(col(Task.id).in_(task_ids)))
    session.delete(project)
    session.commit()
    return Response(status_code=204)


@app.get("/api/tasks")
def list_tasks(
    status: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(
        default="updated_at", pattern="^(created_at|updated_at|title|status|progress)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    conditions = [Task.organization_id == principal.organization_id]
    if status == "ACTIVE":
        conditions.append(col(Task.status).not_in({
            TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED,
        }))
    elif status:
        try:
            conditions.append(Task.status == TaskStatus(status))
        except ValueError as exc:
            raise HTTPException(422, f"Unknown task status: {status}") from exc
    if query and query.strip():
        search = f"%{query.strip()}%"
        conditions.append(or_(Task.id.ilike(search), Task.title.ilike(search)))

    total = session.exec(
        select(func.count()).select_from(Task).where(*conditions)
    ).one()
    sort_column = getattr(Task, sort_by)
    ordering = col(sort_column).asc(
    ) if sort_order == "asc" else col(sort_column).desc()
    items = session.exec(
        select(Task).where(*conditions).order_by(ordering, col(Task.id).desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    status_counts = dict(session.exec(
        select(Task.status, func.count()).where(
            Task.organization_id == principal.organization_id
        ).group_by(Task.status)
    ).all())
    terminal_count = sum(status_counts.get(item, 0) for item in (
        TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED,
    ))
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": {
            "active": sum(status_counts.values()) - terminal_count,
            "awaiting_approval": status_counts.get(TaskStatus.AWAITING_APPROVAL, 0),
            "done": status_counts.get(TaskStatus.DONE, 0),
            "failed": status_counts.get(TaskStatus.FAILED, 0),
        },
    }


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
        workflow = get_definition("workflows", payload.workflow_id)["data"]
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc
    if workflow.get("status") != "active":
        raise HTTPException(409, "Only active workflows can run tasks")
    stage_agents = [
        str(stage["agent"]) for stage in workflow.get("stages", [])
    ]
    default_agent = str(workflow.get("default_agent") or payload.agent_id)
    agent_ids = list(dict.fromkeys(stage_agents or [default_agent]))
    agent_definitions = {}
    identities = {}
    for agent_id in agent_ids:
        identifier = agent_id.removeprefix("did:local:")
        try:
            agent = get_definition("agents", identifier)["data"]
        except RegistryError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not agent_can_execute(agent):
            raise HTTPException(
                409,
                f"Workflow agent {agent_id} must be promoted or have an "
                "administrator-approved evaluation bypass before it can run tasks",
            )
        agent_definitions[agent_id] = agent
        try:
            identities[agent_id] = agent_identity_service.enroll(
                session, identifier, agent, principal,
            )
            agent_identity_service.verify(
                session, identifier, principal.organization_id, agent,
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
    task_values = payload.model_dump()
    task_agent_id = workflow_owner_agent(
        workflow, agent_definitions, default_agent
    )
    task_values["agent_id"] = task_agent_id
    task = Task(
        id=f"TASK-{next_id:03d}", **task_values,
        organization_id=principal.organization_id, created_by=principal.user_id,
    )
    task.branch = f"feature/{task.id.lower()}"
    session.add(task)
    session.commit()
    session.refresh(task)
    session.add(TaskArtifact(
        task_id=task.id,
        kind="workflow-definition",
        content={
            "workflow_id": payload.workflow_id,
            "workflow_version": workflow.get("version"),
            "definition": workflow,
        },
    ))
    session.commit()
    await record_event(session, task.id, "task.created", "Task created", task.title)
    await record_event(
        session,
        task.id,
        "agent.identity_verified",
        "AgentMesh identity verified",
        identities[task_agent_id].did,
        data={
            "agent_did": identities[task_agent_id].did,
            "workflow_id": task.workflow_id,
            "workflow_agents": agent_ids,
            "organization_id": principal.organization_id,
        },
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
    try:
        execution = schedule_task(task_id)
    except ExecutionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "status": "started",
        "task_id": task_id,
        "execution_job_id": getattr(execution, "id", None),
    }


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
        "User requested task cancellation", "warning",
    )
    return task


@app.post("/api/tasks/{task_id}/runtime-elevation")
async def elevate_task_runtime(
    task_id: str,
    payload: RuntimeElevationRequest,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("approval.decide")),
) -> dict:
    task = _scoped_task(session, task_id, principal)
    if not task:
        raise HTTPException(404, "Task not found")
    try:
        return await request_runtime_elevation(
            session,
            task,
            target_tier=payload.target_tier,
            ttl_seconds=payload.ttl_seconds,
            reason=payload.reason,
            attestation=payload.attestation,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


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
    try:
        if approval.action == "git.commit":
            await complete_approval(approval.task_id)
        elif approval.action == "repository.publish":
            await complete_publication(
                approval.task_id,
                str(approval.scope["branch"]),
                bool(approval.scope.get("create_pull_request")),
                principal.user_id,
            )
        else:
            raise HTTPException(
                409, f"Unsupported approval action: {approval.action}")
    except RepositoryError as exc:
        raise HTTPException(502, str(exc)) from exc
    approval.status = "APPROVED"
    approval.approver_id = principal.user_id
    approval.decided_at = datetime.now(UTC)
    session.add(approval)
    session.commit()
    await record_event(
        session, approval.task_id, "approval.approved", "Approval granted", approval.action
    )
    session.refresh(approval)
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
    project = session.get(Project, task.project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        validate_publication(project, payload.create_pull_request)
    except RepositoryError as exc:
        raise HTTPException(409, str(exc)) from exc
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
    owner: str,
    connector_id: str | None = None,
    query: str | None = Query(default=None, max_length=100),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    if connector_id and not github_credentials.get_connector(
        connector_id, principal.organization_id
    ):
        raise HTTPException(404, "Connector not found")
    try:
        repositories = await list_github_repositories(
            owner,
            principal.organization_id,
            principal.user_id,
            connector_id,
            query,
        )
    except (RepositoryError, httpx.HTTPError) as exc:
        raise HTTPException(502, str(exc)) from exc
    credential = github_credentials.status(
        principal.organization_id, principal.user_id
    )
    return {"owner": owner, "repositories": repositories, **credential}


@app.get("/api/connectors")
def list_connectors(
    principal: Principal = Depends(require_permission("read")),
) -> list[dict]:
    return [
        _connector_payload(item)
        for item in github_credentials.connectors(principal.organization_id)
    ]


@app.get("/api/connectors/{connector_id}/accounts")
def connector_accounts(
    connector_id: str,
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    connector = github_credentials.get_connector(
        connector_id, principal.organization_id
    )
    if not connector:
        raise HTTPException(404, "Connector not found")
    installations = github_credentials.installations(
        principal.organization_id, connector_id=connector_id
    )
    return {
        "connector": _connector_payload(connector),
        "accounts": [
            {
                "login": item.account_login,
                "type": item.account_type,
                "installation_id": item.installation_id,
                "repository_selection": item.repository_selection,
            }
            for item in installations
        ],
    }


@app.get("/api/connectors/{connector_id}/repositories")
async def connector_repositories(
    connector_id: str,
    account: str,
    query: str | None = Query(default=None, max_length=100),
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    connector = github_credentials.get_connector(
        connector_id, principal.organization_id
    )
    if not connector:
        raise HTTPException(404, "Connector not found")
    if connector.provider != "github":
        raise HTTPException(
            501, f"{connector.provider} discovery is not implemented")
    try:
        repositories = await list_github_repositories(
            account,
            principal.organization_id,
            principal.user_id,
            connector_id,
            query,
        )
    except (RepositoryError, httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"connector_id": connector_id, "account": account, "repositories": repositories}


@app.post("/api/connectors/{connector_id}/verify")
async def verify_connector(
    connector_id: str,
    principal: Principal = Depends(require_permission("project.create")),
) -> dict:
    connector = github_credentials.get_connector(
        connector_id, principal.organization_id
    )
    if not connector:
        raise HTTPException(404, "Connector not found")
    if connector.provider != "github":
        raise HTTPException(
            501, f"{connector.provider} verification is not implemented")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.github.com/app",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {github_credentials.app_jwt(connector_id)}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(
            502, f"GitHub connection verification failed: {exc}") from exc
    return {"verified": True, "app": response.json().get("slug"), "status": connector.status}


@app.delete("/api/connectors/{connector_id}", status_code=204)
def delete_connector(
    connector_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("project.create")),
) -> Response:
    in_use = session.exec(select(Project).where(
        Project.organization_id == principal.organization_id,
        Project.connector_id == connector_id,
    )).first()
    if in_use:
        raise HTTPException(
            409, "Remove repositories using this connection first")
    if not github_credentials.delete_connector(
        connector_id, principal.organization_id
    ):
        raise HTTPException(404, "Connector not found")
    return Response(status_code=204)


@app.get("/api/connectors/github/manifest/start", response_class=HTMLResponse)
def start_github_manifest(
    name: str = Query(default="AutoDev", min_length=2, max_length=60),
    organization: str | None = Query(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$"
    ),
    principal: Principal = Depends(require_permission("project.create")),
) -> HTMLResponse:
    settings = get_settings()
    connector = github_credentials.create_manifest_connector(
        principal.organization_id, principal.user_id, name
    )
    app_name = _github_manifest_app_name(name, connector.id)
    state = github_credentials.create_state(
        principal.organization_id,
        principal.user_id,
        {"flow": "github_manifest", "connector_id": connector.id},
        expires_in_seconds=3600,
    )
    callback_origin = settings.web_app_url.rstrip("/")
    manifest = {
        "name": app_name,
        "url": callback_origin,
        "redirect_url": (
            f"{callback_origin}/api/connectors/github/manifest/callback"
        ),
        "callback_urls": [
            f"{callback_origin}/api/connectors/github/install/callback"
        ],
        "public": False,
        "request_oauth_on_install": True,
        "default_events": [],
        "default_permissions": {
            "actions": "read",
            "checks": "read",
            "contents": "write",
            "metadata": "read",
            "pull_requests": "write",
            "workflows": "write",
        },
    }
    target = (
        f"https://github.com/organizations/{quote(organization, safe='')}/settings/apps/new"
        if organization
        else "https://github.com/settings/apps/new"
    )
    form = (
        "<!doctype html><html><body><p>Redirecting to GitHub…</p>"
        f'<form id="manifest" method="post" action="{target}?state={quote(state, safe="")}">'
        f'<input type="hidden" name="manifest" value="{html.escape(json.dumps(manifest), quote=True)}">'
        "</form><script>document.getElementById('manifest').submit()</script></body></html>"
    )
    response = HTMLResponse(form)
    response.set_cookie(
        "workbench_github_manifest_state",
        state,
        max_age=3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/connectors/github/manifest",
    )
    return response


@app.get("/api/connectors/github/manifest/callback")
async def github_manifest_callback(
    request: Request,
    code: str,
    state: str,
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    cookie_state = request.cookies.get("workbench_github_manifest_state")
    context = (
        github_credentials.consume_state_context(
            state, principal.organization_id, principal.user_id
        )
        if cookie_state and secrets.compare_digest(cookie_state, state)
        else None
    )
    if not context or context.get("flow") != "github_manifest":
        raise HTTPException(400, "GitHub manifest state is invalid or expired")
    connector_id = str(context.get("connector_id") or "")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.github.com/app-manifests/{quote(code, safe='')}/conversions",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
        connector = github_credentials.complete_manifest(
            connector_id, principal.organization_id, response.json()
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        github_credentials.set_connector_status(
            connector_id, principal.organization_id, "FAILED"
        )
        raise HTTPException(
            502, f"GitHub App registration failed: {exc}") from exc
    redirect = RedirectResponse(
        f"{get_settings().web_app_url.rstrip('/')}/connectors?github=app-created&connector={quote(connector.id, safe='')}",
        status_code=303,
    )
    redirect.delete_cookie(
        "workbench_github_manifest_state",
        path="/api/connectors/github/manifest",
    )
    return redirect


@app.get("/api/connectors/{connector_id}/github/install")
def start_connector_installation(
    connector_id: str,
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    try:
        app_configuration = github_credentials.connector_app(
            connector_id, principal.organization_id
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    state = github_credentials.create_state(
        principal.organization_id,
        principal.user_id,
        {"flow": "github_install", "connector_id": connector_id},
        expires_in_seconds=3600,
    )
    response = RedirectResponse(
        f"https://github.com/apps/{quote(app_configuration['app_slug'], safe='')}/installations/new?{urlencode({'state': state})}"
    )
    response.set_cookie(
        "workbench_github_install_state",
        state,
        max_age=3600,
        httponly=True,
        secure=get_settings().session_cookie_secure,
        samesite="lax",
        path="/api/connectors/github/install",
    )
    return response


@app.get("/api/connectors/github/install/callback")
async def connector_installation_callback(
    request: Request,
    code: str,
    installation_id: int,
    state: str,
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    cookie_state = request.cookies.get("workbench_github_install_state")
    context = (
        github_credentials.consume_state_context(
            state, principal.organization_id, principal.user_id
        )
        if cookie_state and secrets.compare_digest(cookie_state, state)
        else None
    )
    if not context or context.get("flow") != "github_install":
        raise HTTPException(
            400, "GitHub installation state is invalid or expired")
    connector_id = str(context.get("connector_id") or "")
    try:
        app_configuration = github_credentials.connector_app(
            connector_id, principal.organization_id
        )
        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": app_configuration["client_id"],
                    "client_secret": app_configuration["client_secret"],
                    "code": code,
                    "state": state,
                },
            )
            token_response.raise_for_status()
            user_token = token_response.json().get("access_token")
            if not user_token:
                raise RuntimeError("GitHub did not issue a user access token")
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {user_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            installations_response = await client.get(
                "https://api.github.com/user/installations", headers=headers
            )
            installations_response.raise_for_status()
            installation = next(
                (
                    item
                    for item in installations_response.json().get("installations", [])
                    if int(item.get("id", 0)) == installation_id
                    and str(item.get("app_id")) == app_configuration["app_id"]
                ),
                None,
            )
            if not installation:
                raise RuntimeError(
                    "The GitHub App installation is not accessible to this user"
                )
            bot_response = await client.get(
                f"https://api.github.com/users/{quote(app_configuration['app_slug'] + '[bot]', safe='')}",
                headers=headers,
            )
            bot_response.raise_for_status()
        installation["bot_id"] = bot_response.json().get("id")
        github_credentials.connect_installation(
            principal.organization_id,
            principal.user_id,
            installation,
            connector_id,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(
            502, f"GitHub App installation failed: {exc}") from exc
    redirect = RedirectResponse(
        f"{get_settings().web_app_url.rstrip('/')}/connectors?github=installed&connector={quote(connector_id, safe='')}",
        status_code=303,
    )
    redirect.delete_cookie(
        "workbench_github_install_state",
        path="/api/connectors/github/install",
    )
    return redirect


@app.post("/api/connectors/github/repo")
async def github_repository(
    payload: GitHubUrlConnect,
    principal: Principal = Depends(require_permission("project.create")),
) -> dict:
    try:
        return await get_github_repository(
            payload.url, principal.organization_id, principal.user_id
        )
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
    state = github_credentials.create_state(
        principal.organization_id, principal.user_id
    )
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


@app.get("/api/connectors/github/app/start")
def start_github_app_installation(
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    settings = get_settings()
    if not github_credentials.app_install_configured or not settings.github_app_slug:
        raise HTTPException(503, "GitHub App installation is not configured")
    state = github_credentials.create_state(
        principal.organization_id, principal.user_id
    )
    query = urlencode({"state": state})
    response = RedirectResponse(
        f"https://github.com/apps/{settings.github_app_slug}/installations/new?{query}"
    )
    response.set_cookie(
        "workbench_github_app_state",
        state,
        max_age=600,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/api/connectors/github/app",
    )
    return response


@app.get("/api/connectors/github/app/callback")
async def github_app_callback(
    request: Request,
    code: str,
    installation_id: int,
    state: str,
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    cookie_state = request.cookies.get("workbench_github_app_state")
    if (
        not cookie_state
        or not secrets.compare_digest(cookie_state, state)
        or not github_credentials.consume_state(
            state, principal.organization_id, principal.user_id
        )
    ):
        raise HTTPException(400, "GitHub App state is invalid or expired")
    settings = get_settings()
    if not github_credentials.app_install_configured:
        raise HTTPException(503, "GitHub App installation is not configured")
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_app_client_id,
                "client_secret": settings.github_app_client_secret,
                "code": code,
                "state": state,
            },
        )
        token_response.raise_for_status()
        user_token = token_response.json().get("access_token")
        if not user_token:
            raise HTTPException(
                400, "GitHub did not issue a user access token")
        installations_response = await client.get(
            "https://api.github.com/user/installations",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {user_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        installations_response.raise_for_status()
    installation = next(
        (
            item
            for item in installations_response.json().get("installations", [])
            if int(item.get("id", 0)) == installation_id
            and str(item.get("app_id")) == str(settings.github_app_id)
        ),
        None,
    )
    if not installation:
        raise HTTPException(
            403, "The GitHub App installation is not accessible to this user"
        )
    async with httpx.AsyncClient(timeout=20) as client:
        bot_response = await client.get(
            f"https://api.github.com/users/{settings.github_app_slug}%5Bbot%5D",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {user_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        bot_response.raise_for_status()
    installation["bot_id"] = bot_response.json().get("id")
    github_credentials.connect_installation(
        principal.organization_id,
        principal.user_id,
        installation,
    )
    response = RedirectResponse(
        f"{settings.web_app_url.rstrip('/')}?github=app-installed", status_code=303
    )
    response.delete_cookie(
        "workbench_github_app_state", path="/api/connectors/github/app"
    )
    return response


@app.get("/api/connectors/github/oauth/callback")
async def github_oauth_callback(
    request: Request,
    code: str,
    state: str,
    principal: Principal = Depends(require_permission("project.create")),
) -> RedirectResponse:
    cookie_state = request.cookies.get("workbench_github_oauth_state")
    if (
        not cookie_state
        or not secrets.compare_digest(cookie_state, state)
        or not github_credentials.consume_state(
            state, principal.organization_id, principal.user_id
        )
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
    github_credentials.connect(
        principal.organization_id,
        principal.user_id,
        user_response.json()["login"],
        token,
    )
    response = RedirectResponse(
        f"{settings.web_app_url.rstrip('/')}?github=connected", status_code=303)
    response.delete_cookie("workbench_github_oauth_state",
                           path="/api/connectors/github/oauth")
    return response


@app.post("/api/connectors/github/disconnect")
def disconnect_github(
    principal: Principal = Depends(require_permission("project.create")),
) -> dict:
    github_credentials.disconnect(principal.organization_id, principal.user_id)
    return github_credentials.status(principal.organization_id, principal.user_id)


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
    github_status = github_credentials.status(
        principal.organization_id, principal.user_id
    )
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
        "github_authenticated": github_status["authenticated"],
        "github_login": github_status["login"],
        "github_auth_method": github_status["method"],
        "github_app_slug": github_status.get("app_slug"),
        "github_installations": github_status.get("installations", []),
        "github_app_configured": bool(
            github_credentials.connectors(principal.organization_id)
        ) or github_credentials.app_install_configured,
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


@app.websocket("/api/events/ws")
async def events_socket(
    websocket: WebSocket,
    principal: Principal = Depends(require_permission("read")),
):
    await event_hub.connect(
        websocket,
        principal.organization_id,
        cursor=websocket.query_params.get("cursor"),
    )
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
    await event_hub.connect(
        websocket,
        principal.organization_id,
        task_id,
        cursor=websocket.query_params.get("cursor"),
    )
    try:
        await websocket.send_json({"event": "connected", "task_id": task_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_hub.disconnect(websocket)


@app.websocket("/api/evaluations/{run_id}/events/ws")
async def evaluation_events_socket(
    websocket: WebSocket,
    run_id: str,
    principal: Principal = Depends(require_permission("read")),
):
    with Session(engine) as session:
        run = session.get(EvaluationRun, run_id)
        if not run or run.organization_id != principal.organization_id:
            await websocket.close(code=4404, reason="Evaluation run not found")
            return
    await event_hub.connect(
        websocket,
        principal.organization_id,
        run_id,
        cursor=websocket.query_params.get("cursor"),
    )
    try:
        await websocket.send_json({"event": "connected", "run_id": run_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_hub.disconnect(websocket)
