from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, select

from .agent_identity import AgentIdentityError, agent_identity_service
from .auth import Principal
from .models import Approval, Event, Message, Sandbox, Task, TaskArtifact, TaskStatus
from .registry import RegistryError, get_definition
from .workflow import record_event, start_task


class SessionServiceError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _task(session: Session, task_id: str, principal: Principal) -> Task | None:
    return session.exec(select(Task).where(
        Task.id == task_id,
        Task.organization_id == principal.organization_id,
    )).first()


def list_durable_sessions(session: Session, principal: Principal) -> list[dict[str, Any]]:
    tasks = session.exec(select(Task).where(
        Task.organization_id == principal.organization_id
    ).order_by(col(Task.updated_at).desc())).all()
    return [{
        "id": task.id,
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "agent_id": task.agent_id,
        "workspace_persisted": bool(session.exec(select(Sandbox).where(
            Sandbox.task_id == task.id,
            Sandbox.host_workspace.is_not(None),
        )).first()),
        "updated_at": task.updated_at,
    } for task in tasks]


def get_durable_session(
    session: Session, task_id: str, principal: Principal
) -> dict[str, Any]:
    task = _task(session, task_id, principal)
    if not task:
        raise SessionServiceError(404, "Session not found")
    sandbox = session.exec(select(Sandbox).where(
        Sandbox.task_id == task_id)).first()
    events = session.exec(select(Event).where(
        Event.task_id == task_id
    ).order_by(Event.created_at)).all()
    messages = session.exec(select(Message).where(
        Message.task_id == task_id
    ).order_by(Message.created_at)).all()
    artifacts = session.exec(select(TaskArtifact).where(
        TaskArtifact.task_id == task_id
    ).order_by(TaskArtifact.created_at)).all()
    return {
        "id": task.id,
        "task": task,
        "workspace": sandbox.host_workspace if sandbox else None,
        "events": events,
        "messages": messages,
        "outputs": {item.kind: item.content for item in artifacts},
    }


async def continue_durable_session(
    session: Session,
    task_id: str,
    content: str,
    agent_id: str | None,
    principal: Principal,
) -> dict[str, Any]:
    task = _task(session, task_id, principal)
    if not task:
        raise SessionServiceError(404, "Session not found")
    if task.status not in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        raise SessionServiceError(
            409, "Session can continue only after its current run is terminal"
        )
    pending = session.exec(select(Approval).where(
        Approval.task_id == task_id,
        Approval.status == "PENDING",
    )).first()
    if pending:
        raise SessionServiceError(
            409, "Resolve the pending approval before continuing the session"
        )
    if agent_id:
        identifier = agent_id.removeprefix("did:local:")
        try:
            definition = get_definition("agents", identifier)["data"]
        except RegistryError as exc:
            raise SessionServiceError(422, str(exc)) from exc
        if definition.get("status") != "promoted":
            raise SessionServiceError(
                409, "Only promoted agent versions can continue sessions"
            )
        try:
            agent_identity_service.verify(
                session,
                identifier,
                principal.organization_id,
                definition,
            )
        except AgentIdentityError as exc:
            raise SessionServiceError(409, str(exc)) from exc
        task.agent_id = agent_id
    message = Message(task_id=task_id, role="user", content=content)
    task.status = TaskStatus.FAILED
    task.phase = "Follow-up queued"
    task.progress = 0
    task.updated_at = datetime.now(UTC)
    session.add(message)
    session.add(task)
    session.commit()
    await record_event(
        session,
        task_id,
        "session.continued",
        "Session follow-up queued",
        "A fresh sandbox will continue from the persisted worktree",
        data={"agent_id": task.agent_id},
    )
    start_task(task_id)
    return {"status": "started", "session_id": task_id, "agent_id": task.agent_id}
