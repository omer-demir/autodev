import asyncio
import json
import logging
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry import context, trace
from opentelemetry.trace import Status, StatusCode
from sqlmodel import Session, select

from .agent import AgentRuntime
from .agent_identity import agent_identity_service
from .config import get_settings
from .database import engine
from .execution_queue import enqueue_execution, request_execution_cancellation
from .events import event_hub
from .evidence import evidence_provider
from .models import Approval, Event, Message, Project, Sandbox, Task, TaskArtifact, TaskStatus
from .model_recovery import ModelRecoveryDecision, model_recovery_broker
from .observability import mark_error, observe_event, observe_session, tracer
from .providers import Decision, get_governance_provider, get_sandbox_provider
from .reliability import reliability
from .repositories import (
    create_github_pull_request,
    materialize_repository,
    parse_github_url,
    publish_repository,
    validate_publication,
)
from .github_auth import github_credentials
from .registry import get_definition
from .runtime_supervision import ExecutionTier
from .workflow_orchestration import (
    assert_parallel_stages_are_read_only,
    stage_artifact_inputs,
    stage_waves,
)
from .workflow_supervisor import workflow_supervisor
from .workspace_snapshots import workspace_snapshots


governance = get_governance_provider()
sandbox_provider = get_sandbox_provider()
running_tasks: dict[str, asyncio.Task[None]] = {}
logger = logging.getLogger("uvicorn.error")

_LOG_FIELDS = {
    "provider", "model", "framework", "fallback", "latency_ms", "duration",
    "exit_code", "capability", "decision", "policy", "reason", "trace_id", "span_id",
}


def _log_event(task_id: str, event_type: str, title: str, severity: str, data: dict) -> None:
    """Emit bounded event metadata without prompts, source, commands, paths, or tool output."""
    metadata = {key: value for key,
                value in data.items() if key in _LOG_FIELDS}
    message = "task_event task=%s event=%s severity=%s title=%s metadata=%s"
    level = (
        logging.ERROR
        if severity == "error"
        else logging.WARNING if severity == "warning" else logging.INFO
    )
    logger.log(level, message, task_id, event_type, severity,
               title, json.dumps(metadata, default=str))


async def record_event(
    session: Session,
    task_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    severity: str = "info",
    data: dict | None = None,
) -> Event:
    event_data = dict(data or {})
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_data["trace_id"] = trace.format_trace_id(span_context.trace_id)
        event_data["span_id"] = trace.format_span_id(span_context.span_id)
    event = Event(task_id=task_id, type=event_type, title=title,
                  detail=detail, severity=severity, data=event_data)
    session.add(event)
    session.commit()
    session.refresh(event)
    observe_event(event_type, severity, event_data)
    reliability.observe_event(event_type, {"task_id": task_id, **event_data})
    _log_event(task_id, event_type, title, severity, event_data)
    task = session.get(Task, task_id)
    await event_hub.publish({
        "event": event_type,
        "task_id": task_id,
        "organization_id": task.organization_id if task else None,
        "id": event.id,
    })
    return event


async def recover_interrupted_tasks() -> None:
    """Fail active database tasks whose in-memory runner was lost during a restart."""
    inactive = {
        TaskStatus.DRAFT, TaskStatus.AWAITING_APPROVAL, TaskStatus.DONE,
        TaskStatus.FAILED, TaskStatus.CANCELLED,
    }
    with Session(engine) as session:
        tasks = session.exec(select(Task)).all()
        for task in tasks:
            if task.status in inactive or task.id in running_tasks:
                continue
            previous_status = task.status
            task.status = TaskStatus.FAILED
            task.phase = "Failed"
            task.updated_at = datetime.now(UTC)
            session.add(task)
            session.commit()
            await record_event(
                session,
                task.id,
                "task.interrupted",
                "Task interrupted by API restart",
                "The API restarted without an active in-memory runner; retry the task to continue.",
                "error",
                {"reason": "api_restart",
                    "previous_status": str(previous_status)},
            )
            await cleanup_sandbox(session, task.id, "API restart recovery")


async def update_phase(session: Session, task: Task, status: TaskStatus, phase: str, progress: int) -> None:
    transition = await workflow_supervisor.transition(
        task.id, task.agent_id, status, task.progress
    )
    task.status = status
    task.phase = transition.label
    task.progress = transition.progress
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    artifact = session.exec(
        select(TaskArtifact).where(
            TaskArtifact.task_id == task.id,
            TaskArtifact.kind == "runtime-supervision",
        )
    ).first()
    content = dict(artifact.content) if artifact else {}
    history = list(content.get("transitions", []))
    history.append({
        "phase_id": transition.phase_id,
        "status": status.value,
        "recorded_at": datetime.now(UTC).isoformat(),
        **transition.supervision["transition"],
    })
    content.update({
        "provider": transition.supervision["provider"],
        "provider_version": transition.supervision["provider_version"],
        "capabilities": transition.supervision["capabilities"],
        "session_id": transition.session_id,
        "saga_id": transition.saga_id,
        "tier": transition.supervision["tier"],
        "trust_score": transition.supervision["trust_score"],
        "transitions": history,
    })
    if transition.supervision["termination"]:
        content["termination"] = transition.supervision["termination"]
    await _save_artifact(session, task.id, "runtime-supervision", content)
    await record_event(
        session,
        task.id,
        "runtime_supervision.transition",
        f"Runtime supervisor entered {transition.label}",
        transition.phase_id,
        data={
            "provider": transition.supervision["provider"],
            "provider_version": transition.supervision["provider_version"],
            "tier": transition.supervision["tier"],
            "phase_id": transition.phase_id,
            "audit_commitment": (
                transition.supervision["termination"] or {}
            ).get("audit_commitment"),
        },
    )
    await event_hub.publish({
        "event": "task.updated",
        "task_id": task.id,
        "organization_id": task.organization_id,
    })


async def cleanup_sandbox(session: Session, task_id: str, reason: str) -> bool:
    """Remove a task container without deleting its host worktree or evidence."""
    sandbox = session.exec(select(Sandbox).where(
        Sandbox.task_id == task_id)).first()
    if not sandbox or sandbox.status == "KILLED":
        return True
    try:
        if sandbox.container_id:
            await sandbox_provider.kill(sandbox.container_id)
        sandbox.status = "KILLED"
        session.add(sandbox)
        session.commit()
        await record_event(
            session,
            task_id,
            "sandbox.killed",
            "Sandbox removed",
            f"Sandbox removed after {reason}; the worktree and evidence remain available",
            data={"reason": reason, "container_id": sandbox.container_id},
        )
        return True
    except Exception as exc:
        session.rollback()
        await record_event(
            session,
            task_id,
            "sandbox.cleanup_failed",
            "Sandbox cleanup failed",
            str(exc),
            "warning",
            {"reason": reason, "container_id": sandbox.container_id},
        )
        return False


async def _save_artifact(
    session: Session,
    task_id: str,
    kind: str,
    content: dict[str, Any],
) -> None:
    artifact = session.exec(
        select(TaskArtifact).where(TaskArtifact.task_id ==
                                   task_id, TaskArtifact.kind == kind)
    ).first()
    if artifact:
        artifact.content = content
    else:
        artifact = TaskArtifact(task_id=task_id, kind=kind, content=content)
    session.add(artifact)
    session.commit()
    evidence_provider.write(task_id, kind, content)
    task = session.get(Task, task_id)
    await event_hub.publish({
        "event": "artifact.updated",
        "task_id": task_id,
        "organization_id": task.organization_id if task else None,
        "kind": kind,
    })


async def request_runtime_elevation(
    session: Session,
    task: Task,
    *,
    target_tier: int,
    ttl_seconds: int,
    reason: str,
    attestation: str | None,
) -> dict[str, Any]:
    grant = await workflow_supervisor.elevate(
        task.id,
        target_tier=ExecutionTier(target_tier),
        ttl_seconds=ttl_seconds,
        reason=reason,
        attestation=attestation,
    )
    evidence = {
        "provider": grant.provider,
        "grant_id": grant.grant_id,
        "original_tier": grant.original_tier.value,
        "elevated_tier": grant.elevated_tier.value,
        "expires_at": grant.expires_at.isoformat(),
        "evidence": grant.evidence,
    }
    artifact = session.exec(
        select(TaskArtifact).where(
            TaskArtifact.task_id == task.id,
            TaskArtifact.kind == "runtime-supervision",
        )
    ).first()
    content = dict(artifact.content) if artifact else {}
    elevations = list(content.get("elevations", []))
    elevations.append(evidence)
    content["elevations"] = elevations
    await _save_artifact(session, task.id, "runtime-supervision", content)
    await record_event(
        session,
        task.id,
        "runtime_supervision.elevated",
        f"Runtime tier elevated to {grant.elevated_tier.value}",
        reason,
        "warning",
        data=evidence,
    )
    return evidence


def _git(workspace: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=workspace, text=True, capture_output=True, timeout=120,
        check=False,
    )


def _collect_changes(workspace: Path) -> dict[str, Any]:
    _git(workspace, ["add", "-N", "."])
    status = _git(workspace, ["status", "--porcelain"])
    diff = _git(workspace, ["diff", "--no-ext-diff", "--binary"])
    numstat = _git(workspace, ["diff", "--numstat"])
    numbers: dict[str, tuple[int, int]] = {}
    for line in numstat.stdout.splitlines():
        added, deleted, path = line.split("\t", 2)
        numbers[path] = (int(added) if added.isdigit() else 0,
                         int(deleted) if deleted.isdigit() else 0)
    files = []
    for line in status.stdout.splitlines():
        code, path = line[:2].strip() or "modified", line[3:]
        added, deleted = numbers.get(path, (0, 0))
        files.append({
            "path": path,
            "status": {"A": "added", "D": "deleted"}.get(code[-1:], "modified"),
            "additions": added,
            "deletions": deleted,
        })
    return {"files": files, "diff": diff.stdout[-500_000:], "status": status.stdout}


async def _run_security(workspace: Path) -> dict[str, Any]:
    commands = {
        "Semgrep": ["semgrep", "scan", "--config", "auto", "--json", str(workspace)],
        "Trivy": ["trivy", "fs", "--format", "json", str(workspace)],
        "Gitleaks": ["gitleaks", "detect", "--source", str(workspace), "--report-format", "json", "--no-banner"],
    }
    results: dict[str, Any] = {}
    for name, command in commands.items():
        if not shutil.which(command[0]):
            results[name] = {"status": "unavailable", "exit_code": None,
                             "output": f"{command[0]} is not installed"}
            continue
        started = time.monotonic()
        completed = await asyncio.to_thread(
            subprocess.run, command, text=True, capture_output=True, timeout=300
        )
        results[name] = {
            "status": "passed" if completed.returncode == 0 else "findings",
            "exit_code": completed.returncode,
            "duration": round(time.monotonic() - started, 2),
            "output": (completed.stdout + completed.stderr)[-100_000:],
        }
    return {
        "high": 0,
        "medium": sum(item["status"] == "findings" for item in results.values()),
        "low": 0,
        "scanners": {name: item["status"] for name, item in results.items()},
        "details": results,
    }


async def _run_executable_workflow(
    *,
    session: Session,
    task: Task,
    workflow: dict[str, Any],
    workspace: Path,
    container_id: str,
    model_name: str,
    callback: Any,
    steering: list[str],
    session_context: list[str],
    steering_provider: Any,
    model_recovery: Any,
) -> str:
    waves = stage_waves(workflow)
    agent_definitions = {
        str(stage["agent"]): get_definition(
            "agents", str(stage["agent"]).removeprefix("did:local:")
        )["data"]
        for wave in waves for stage in wave
    }
    assert_parallel_stages_are_read_only(waves, agent_definitions)
    artifact_values: dict[str, dict[str, Any]] = {}
    run_state: dict[str, Any] = {
        "workflow_id": task.workflow_id,
        "workflow_version": workflow["version"],
        "status": "running",
        "stages": {},
    }
    persistence_lock = asyncio.Lock()
    await _save_artifact(session, task.id, "workflow-run", run_state)

    async def run_stage(stage: dict[str, Any]) -> tuple[dict[str, Any], str]:
        stage_id = str(stage["id"])
        agent_id = str(stage["agent"])
        definition_id = agent_id.removeprefix("did:local:")
        verified = agent_identity_service.verify(
            session,
            definition_id,
            task.organization_id,
            agent_definitions[agent_id],
        )
        input_artifacts = stage_artifact_inputs(stage, artifact_values)
        async with persistence_lock:
            await record_event(
                session,
                task.id,
                "workflow.stage_started",
                f"Workflow stage started: {stage_id}",
                str(stage["responsibility"]),
                data={
                    "workflow_id": task.workflow_id,
                    "stage_id": stage_id,
                    "agent_id": agent_id,
                    "agent_did": verified.did,
                },
            )

        async def stage_callback(
            event_type: str,
            title: str,
            detail: str,
            severity: str,
            data: dict[str, Any] | None,
        ) -> None:
            async with persistence_lock:
                await callback(event_type, title, detail, severity, {
                    **(data or {}),
                    "workflow_id": task.workflow_id,
                    "stage_id": stage_id,
                    "agent_id": agent_id,
                })

        environment = agent_definitions[agent_id].get("environment", {})
        primary_stage = agent_id == task.agent_id
        stage_container_id = container_id
        if not primary_stage:
            created = await sandbox_provider.create({
                "name": f"agentic-sdlc-{task.id.lower()}-{stage_id}",
                "workspace": str(workspace),
                "image": environment.get("image"),
                "network_mode": environment.get("network_mode", "none"),
                "workspace_access": environment.get("workspace_access", "read-write"),
                "pool_profile": environment.get(
                    "pool_profile", get_settings().azure_session_pool_profile
                ),
                "environment": environment.get("variables", {}),
            })
            stage_container_id = str(created["container_id"])
        try:
            summary = await AgentRuntime().run(
                task_id=task.id,
                title=task.title,
                description=task.description,
                agent_id=agent_id,
                model_name=model_name,
                task_mode=task.mode,
                verbose_logging=task.verbose_logging,
                workspace=workspace,
                container_id=stage_container_id,
                callback=stage_callback,
                stage_context={
                    "workflow_id": task.workflow_id,
                    "stage_id": stage_id,
                    "responsibility": stage["responsibility"],
                    "inputs": list(stage.get("inputs", [])),
                    "input_artifacts": input_artifacts,
                    "expected_outputs": list(stage["outputs"]),
                    "handoff": stage.get("handoff", {}),
                },
                steering=steering,
                session_context=session_context,
                steering_provider=steering_provider,
                model_recovery=model_recovery,
            )
        except Exception as exc:
            run_state["stages"][stage_id] = {
                "status": "failed",
                "agent_id": agent_id,
                "error": str(exc),
            }
            raise
        finally:
            if not primary_stage:
                await sandbox_provider.kill(stage_container_id)
        async with persistence_lock:
            changes = await asyncio.to_thread(_collect_changes, workspace)
            await _save_artifact(session, task.id, "changes", changes)
            await record_event(
                session,
                task.id,
                "workflow.stage_completed",
                f"Workflow stage completed: {stage_id}",
                summary,
                data={
                    "workflow_id": task.workflow_id,
                    "stage_id": stage_id,
                    "agent_id": agent_id,
                    "outputs": list(stage["outputs"]),
                },
            )
        return stage, summary

    final_message = ""
    try:
        for wave_index, wave in enumerate(waves):
            results = await asyncio.gather(*(run_stage(stage) for stage in wave))
            for stage, summary in results:
                stage_id = str(stage["id"])
                outputs = list(stage["outputs"])
                for output_id in outputs:
                    value = {
                        "workflow_id": task.workflow_id,
                        "stage_id": stage_id,
                        "agent_id": stage["agent"],
                        "summary": summary,
                    }
                    artifact_values[output_id] = value
                    await _save_artifact(session, task.id, output_id, value)
                run_state["stages"][stage_id] = {
                    "status": "completed",
                    "wave": wave_index,
                    "agent_id": stage["agent"],
                    "inputs": list(stage.get("inputs", [])),
                    "outputs": outputs,
                    "handoff": {
                        "include": stage.get("handoff", {}).get(
                            "include", ["summary", "artifacts"]
                        ),
                        "summary": summary,
                        "artifacts": outputs,
                    },
                }
                final_message = summary
            await _save_artifact(session, task.id, "workflow-run", run_state)
    except Exception as exc:
        run_state["status"] = "failed"
        run_state["error"] = str(exc)
        await _save_artifact(session, task.id, "workflow-run", run_state)
        raise
    run_state["status"] = "completed"
    await _save_artifact(session, task.id, "workflow-run", run_state)
    return final_message


async def run_task(task_id: str) -> None:
    with Session(engine) as session:
        task = session.get(Task, task_id)
        project = session.get(Project, task.project_id) if task else None
        if not task or not project:
            return
        workspace: Path | None = None
        workspace_revision_id: str | None = None
        session_started = time.monotonic()
        files_changed = 0
        session_span = tracer().start_span(
            "agent.session",
            attributes={
                "autodev.task_id": task.id,
                "autodev.agent_id": task.agent_id,
                "autodev.mode": task.mode,
                "gen_ai.request.model": task.model_name or get_settings().model_name,
            },
        )
        context_token = context.attach(trace.set_span_in_context(session_span))
        try:
            workflow_snapshot = session.exec(
                select(TaskArtifact).where(
                    TaskArtifact.task_id == task.id,
                    TaskArtifact.kind == "workflow-definition",
                )
            ).first()
            workflow_definition = (
                dict(workflow_snapshot.content["definition"])
                if workflow_snapshot and isinstance(
                    workflow_snapshot.content.get("definition"), dict
                )
                else get_definition("workflows", task.workflow_id)["data"]
            )
            definition_id = task.agent_id.removeprefix("did:local:")
            identity_definition = get_definition(
                "agents", definition_id)["data"]
            verified_identity = agent_identity_service.verify(
                session, definition_id, task.organization_id, identity_definition
            )
            await record_event(
                session,
                task_id,
                "agent.identity_verified",
                "AgentMesh identity verified for execution",
                verified_identity.did,
                data={"agent_did": verified_identity.did},
            )
            await update_phase(session, task, TaskStatus.INTAKE, "Repository", 5)
            await record_event(session, task_id, "repository.materializing", "Preparing repository", project.repository_url or project.repository_path)
            workspace_target = Path(
                get_settings().workspace_dir).resolve() / task_id / "repo"
            if workspace_target.exists():
                existing_revision = workspace_snapshots.latest(task_id)
            else:
                existing_revision = await workspace_snapshots.restore_latest(
                    task_id, workspace_target
                )
            if existing_revision:
                workspace_revision_id = existing_revision.id
                await record_event(
                    session,
                    task_id,
                    "workspace.restored",
                    "Workspace revision restored",
                    existing_revision.id,
                    data={"revision_id": existing_revision.id},
                )
            workspace = await materialize_repository(project, task_id)
            task.branch = f"workbench/{task_id.lower()}"
            session.add(task)
            session.commit()
            await record_event(session, task_id, "repository.ready", "Isolated worktree ready", str(workspace))

            agent_definition = get_definition(
                "agents", task.agent_id.removeprefix("did:local:"))["data"]
            environment = agent_definition.get("environment", {})
            sandbox_name = f"agentic-sdlc-{task_id.lower()}"
            created = await sandbox_provider.create({
                "name": sandbox_name,
                "workspace": str(workspace),
                "image": environment.get("image"),
                "network_mode": environment.get("network_mode", "none"),
                "workspace_access": environment.get("workspace_access", "read-write"),
                "pool_profile": environment.get(
                    "pool_profile", get_settings().azure_session_pool_profile
                ),
                "environment": environment.get("variables", {}),
            })
            sandbox = session.exec(select(Sandbox).where(
                Sandbox.task_id == task_id)).first()
            if not sandbox:
                sandbox = Sandbox(
                    id=f"SBX-{task_id.removeprefix('TASK-')}", task_id=task_id)
            sandbox.provider = str(created.get("provider") or "docker")
            sandbox.status = created["status"]
            sandbox.workspace = created["workspace"]
            sandbox.network_policy = created["network_policy"]
            sandbox.container_id = created["container_id"]
            sandbox.host_workspace = str(workspace)
            sandbox.workspace_revision_id = workspace_revision_id
            session.add(sandbox)
            session.commit()
            await record_event(
                session, task_id, "sandbox.created", "Sandbox created",
                f"{sandbox.id} · {sandbox.provider} · session {sandbox.container_id[:12]} · "
                f"profile {created['image']} · network {sandbox.network_policy}",
            )

            await record_event(
                session, task_id, "rpi.research", "RPI research initialized",
                "The isolated repository and governed agent context are ready for bounded evidence gathering",
            )
            await update_phase(session, task, TaskStatus.PLANNING, "Agent", 15)
            plan = {
                "requirements": [task.description],
                "steps": [
                    "Research the controlling repository code and constraints",
                    "Plan the smallest coherent change and focused checks",
                    "Implement the requested task with the selected model",
                    "Review the diff, tests, and deterministic security scans",
                ],
                "acceptance": [
                    "Changes match the task",
                    "Executable checks support the result",
                    "Developer reviews the real diff",
                    "Commit requires scoped approval",
                ],
            }
            await _save_artifact(session, task_id, "rpi-plan", plan)
            await _save_artifact(session, task_id, "plan", plan)
            await record_event(
                session, task_id, "rpi.plan", "RPI plan recorded",
                "Research, implement, validate, and review against explicit acceptance checks",
                data={"artifact": "rpi-plan"},
            )
            model_name = task.model_name or get_settings().model_name
            await record_event(
                session, task_id, "agent.started", "Coding agent started",
                f"{get_settings().model_provider} · {model_name}",
            )

            async def callback(event_type: str, title: str, detail: str, severity: str, data: dict[str, Any] | None) -> None:
                await record_event(session, task_id, event_type, title, detail, severity, data)
                if event_type == "agent.message":
                    session.add(Message(task_id=task_id,
                                role="assistant", content=detail))
                    session.commit()
                if (
                    event_type == "tool.completed"
                    and (data or {}).get("capability") == "repository.write"
                ):
                    live_changes = await asyncio.to_thread(
                        _collect_changes, workspace
                    )
                    await _save_artifact(
                        session, task_id, "changes", live_changes
                    )

            async def steering() -> list[str]:
                session.expire_all()
                return [
                    item.content for item in session.exec(
                        select(Message).where(Message.task_id == task_id,
                                              Message.role == "user").order_by(Message.created_at)
                    ).all()
                ]

            async def recover_model(
                failed_model: str, error: str, attempts: int
            ) -> ModelRecoveryDecision:
                settings = get_settings()
                await update_phase(
                    session, task, TaskStatus.AWAITING_MODEL, "Model recovery", task.progress
                )
                decision_task = asyncio.create_task(model_recovery_broker.request(
                    task_id=task_id,
                    provider=settings.model_provider,
                    model=failed_model,
                    fallback_provider=settings.model_fallback_provider,
                    fallback_model=settings.model_fallback_name,
                    error=error,
                    attempts=attempts,
                    timeout=settings.model_recovery_timeout_seconds,
                ))
                await asyncio.sleep(0)
                await record_event(
                    session, task_id, "model.recovery_required",
                    "Model recovery requires operator decision",
                    "Retry this Copilot turn, choose another Copilot model, use the configured "
                    "Ollama fallback, or cancel the run.",
                    "warning",
                    {
                        "provider": settings.model_provider,
                        "model": failed_model,
                        "fallback_provider": settings.model_fallback_provider,
                        "fallback_model": settings.model_fallback_name,
                        "attempts": attempts,
                    },
                )
                decision = await decision_task
                if decision.action == "change_model" and decision.model:
                    task.model_name = decision.model
                    session.add(task)
                    session.commit()
                await update_phase(
                    session, task, TaskStatus.IMPLEMENTATION, "Implementation", task.progress
                )
                await record_event(
                    session, task_id, "model.recovery_resolved",
                    "Model recovery decision received",
                    decision.action.replace("_", " ").title(),
                    "warning" if decision.action in {
                        "fallback", "cancel"} else "info",
                    {"decision": decision.action,
                        "model": decision.model or failed_model},
                )
                return decision

            session_messages = session.exec(
                select(Message).where(Message.task_id ==
                                      task_id).order_by(Message.created_at)
            ).all()
            initial_steering = [
                item.content for item in session_messages if item.role == "user"
            ]
            session_context = [
                f"{item.role.title()}: {item.content}" for item in session_messages[-20:]
            ]
            await update_phase(session, task, TaskStatus.IMPLEMENTATION, "Implementation", 35)
            if workflow_definition.get("stages"):
                final_message = await _run_executable_workflow(
                    session=session,
                    task=task,
                    workflow=workflow_definition,
                    workspace=workspace,
                    container_id=sandbox.container_id,
                    model_name=model_name,
                    callback=callback,
                    steering=initial_steering,
                    session_context=session_context,
                    steering_provider=steering,
                    model_recovery=recover_model,
                )
            else:
                final_message = await AgentRuntime().run(
                    task_id=task_id,
                    title=task.title,
                    description=task.description,
                    agent_id=task.agent_id,
                    model_name=model_name,
                    task_mode=task.mode,
                    verbose_logging=task.verbose_logging,
                    workspace=workspace,
                    container_id=sandbox.container_id,
                    callback=callback,
                    steering=initial_steering,
                    session_context=session_context,
                    steering_provider=steering,
                    model_recovery=recover_model,
                )
            await record_event(session, task_id, "agent.completed", "Agent implementation completed", final_message)

            changes = await asyncio.to_thread(_collect_changes, workspace)
            files_changed = len(changes["files"])
            await _save_artifact(session, task_id, "changes", changes)
            research_events = session.exec(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "tool.completed",
                ).order_by(Event.id)
            ).all()
            research = {
                "tools": [
                    {"tool": event.title, "detail": event.detail}
                    for event in research_events
                    if event.title in {"list_files", "search_text", "read_file"}
                ],
                "evidence_count": sum(
                    event.title in {"list_files", "search_text", "read_file"}
                    for event in research_events
                ),
            }
            await _save_artifact(session, task_id, "rpi-research", research)
            await _save_artifact(session, task_id, "rpi-implementation", {
                "summary": final_message,
                "files": changes["files"],
                "status": changes["status"],
            })
            await record_event(
                session, task_id, "rpi.implementation", "RPI implementation captured",
                f"{len(changes['files'])} changed files and {research['evidence_count']} research tool results",
                data={"artifacts": ["rpi-research", "rpi-implementation"]},
            )
            await record_event(session, task_id, "file.modified", "Repository changes collected", f"{len(changes['files'])} files changed")

            await update_phase(session, task, TaskStatus.TESTING, "Testing", 65)
            test_events = [
                event for event in session.exec(
                    select(Event).where(
                        Event.task_id == task_id, Event.type == "tool.completed"
                    ).order_by(Event.id)
                ).all()
                if event.data.get("capability") == "test.run"
            ]
            test_results = [event.data.get("result", {})
                            for event in test_events]
            tests = {
                "passed": sum(result.get("exit_code") == 0 for result in test_results),
                "failed": sum(result.get("exit_code") not in {0, None} for result in test_results),
                "skipped": int(not test_results),
                "duration": round(sum(float(result.get("duration", 0)) for result in test_results), 2),
                "output": "\n\n".join(str(result.get("output", "")) for result in test_results)[-100_000:]
                or "The agent did not run a governed test command",
                "commands": [result.get("arguments", []) for result in test_results],
                "exit_code": test_results[-1].get("exit_code") if test_results else None,
            }
            await _save_artifact(session, task_id, "tests", tests)
            await record_event(session, task_id, "test.completed", "Tests completed", tests["output"][-2000:], "info" if tests["exit_code"] in {0, None} else "warning")

            await update_phase(session, task, TaskStatus.SECURITY, "Security", 78)
            security = await _run_security(workspace)
            await _save_artifact(session, task_id, "security", security)
            scanner_summary = ", ".join(
                f"{name}: {status}" for name, status in security["scanners"].items())
            await record_event(session, task_id, "security.completed", "Security scans completed", scanner_summary, "warning" if security["medium"] else "info")

            await update_phase(session, task, TaskStatus.REVIEW, "Review", 88)
            await _save_artifact(session, task_id, "plan", plan)
            review = {
                "summary": final_message,
                "changed_files": len(changes["files"]),
                "tests": {
                    "passed": tests["passed"],
                    "failed": tests["failed"],
                    "skipped": tests["skipped"],
                    "exit_code": tests["exit_code"],
                },
                "security": {
                    "high": security["high"],
                    "medium": security["medium"],
                    "low": security["low"],
                    "scanners": security["scanners"],
                },
                "acceptance": plan["acceptance"],
            }
            await _save_artifact(session, task_id, "rpi-review", review)
            await record_event(
                session, task_id, "rpi.review", "RPI review evidence recorded",
                f"Tests: {tests['passed']} passed, {tests['failed']} failed; security findings: {security['medium']}",
                "warning" if tests["failed"] or security["medium"] else "info",
                {"artifact": "rpi-review"},
            )
            evidence_provider.write(task_id, "governance", {
                                    "policy": "development-v1", "agent": task.agent_id})

            if task.mode == "assessment":
                await update_phase(session, task, TaskStatus.DONE, "Done", 100)
                await record_event(
                    session, task_id, "task.completed", "Assessment completed",
                    "Read-only assessment completed; no repository change or commit was required",
                )
                evidence_provider.write(task_id, "result", {
                    "status": "DONE", "task_id": task_id, "mode": task.mode,
                    "workspace": str(workspace), "summary": final_message,
                })
                return
            decision = await governance.evaluate(task.agent_id, "git.commit", {}, {"task_id": task_id})
            if not changes["files"]:
                raise RuntimeError(
                    "The change task completed without modifying the repository. Use assessment mode for read-only reviews.")
            if decision.decision == Decision.REQUIRE_APPROVAL:
                approval_id = f"APR-{task_id.removeprefix('TASK-')}"
                approval = session.get(Approval, approval_id)
                if not approval:
                    approval = Approval(
                        id=approval_id,
                        task_id=task_id,
                        action="git.commit",
                        organization_id=task.organization_id,
                        requester_id=task.created_by,
                    )
                approval.status = "PENDING"
                approval.scope = {"repository": project.name, "branch": task.branch,
                                  "task_id": task_id, "workspace": str(workspace)}
                session.add(approval)
                session.commit()
                await update_phase(session, task, TaskStatus.AWAITING_APPROVAL, "Approval", 95)
                await record_event(session, task_id, "approval.created", "Commit approval requested", "Review the real worktree diff before authorizing this one commit", "warning")
        except asyncio.CancelledError:
            await update_phase(session, task, TaskStatus.CANCELLED, "Cancelled", task.progress)
            session_span.set_status(Status(StatusCode.ERROR, "cancelled"))
            raise
        except Exception as exc:
            mark_error(session_span, exc)
            await update_phase(session, task, TaskStatus.FAILED, "Failed", task.progress)
            await record_event(session, task_id, "task.failed", "Task failed", str(exc), "error")
        finally:
            if workspace and workspace.exists():
                try:
                    revision = await workspace_snapshots.checkpoint(
                        task_id,
                        task.organization_id,
                        workspace,
                        workspace_revision_id,
                    )
                    sandbox = session.exec(select(Sandbox).where(
                        Sandbox.task_id == task_id
                    )).first()
                    if sandbox:
                        sandbox.workspace_revision_id = revision.id
                        session.add(sandbox)
                        session.commit()
                    await record_event(
                        session,
                        task_id,
                        "workspace.checkpointed",
                        "Workspace revision checkpointed",
                        revision.id,
                        data={"revision_id": revision.id,
                              "digest": revision.digest},
                    )
                except Exception as exc:
                    await record_event(
                        session,
                        task_id,
                        "workspace.checkpoint_failed",
                        "Workspace checkpoint failed",
                        str(exc),
                        "error",
                    )
                    if get_settings().workspace_snapshot_required:
                        task.status = TaskStatus.FAILED
                        task.phase = "Failed"
                        task.updated_at = datetime.now(UTC)
                        session.add(task)
                        session.commit()
            session.expire(task)
            status = str(task.status)
            if status in {"DONE", "FAILED", "CANCELLED"}:
                await cleanup_sandbox(session, task_id, status.casefold())
            if status in {"DONE", "AWAITING_APPROVAL"}:
                session_span.set_status(Status(StatusCode.OK))
            session_span.set_attribute("autodev.status", status)
            duration_ms = round((time.monotonic() - session_started) * 1000)
            observe_session(
                status=status, duration_ms=duration_ms, files_changed=files_changed
            )
            context.detach(context_token)
            session_span.end()
            running_tasks.pop(task_id, None)


def start_task(task_id: str) -> asyncio.Task[None] | Any:
    if get_settings().execution_dispatch == "durable":
        return enqueue_execution(task_id)
    active = running_tasks.get(task_id)
    if active and not active.done():
        return active
    task = asyncio.create_task(run_task(task_id))
    running_tasks[task_id] = task
    return task


async def shutdown_running_tasks() -> None:
    """Cancel active runs and wait for their task/sandbox cleanup before shutdown."""
    active = [(task_id, task)
              for task_id, task in running_tasks.items() if not task.done()]
    for task_id, task in active:
        model_recovery_broker.cancel(task_id)
        task.cancel()
    if active:
        await asyncio.gather(*(task for _, task in active), return_exceptions=True)


async def terminate_task(task_id: str) -> None:
    model_recovery_broker.cancel(task_id)
    request_execution_cancellation(task_id)
    active = running_tasks.get(task_id)
    if active and not active.done():
        active.cancel()
    with Session(engine) as session:
        await cleanup_sandbox(session, task_id, "operator cancellation")


def _pull_request_body(
    task: Task,
    artifacts: dict[str, dict[str, Any]],
    approved_by: str | None,
) -> str:
    changes = artifacts.get("changes", {})
    tests = artifacts.get("tests", {})
    security = artifacts.get("security", {})
    files = list(changes.get("files") or [])
    file_lines = []
    for item in files[:50]:
        path = str(item.get("path") or "unknown").replace("`", "\\`")
        status = str(item.get("status") or "modified")
        additions = int(item.get("additions") or 0)
        deletions = int(item.get("deletions") or 0)
        file_lines.append(
            f"- `{path}` — {status} (+{additions}/-{deletions})"
        )
    if len(files) > 50:
        file_lines.append(f"- …and {len(files) - 50} more files")
    if not file_lines:
        file_lines.append("- No changed-file artifact was recorded.")

    test_summary = (
        f"{int(tests.get('passed') or 0)} passed, "
        f"{int(tests.get('failed') or 0)} failed, "
        f"{int(tests.get('skipped') or 0)} skipped"
    )
    scanners = security.get("scanners") or {}
    scanner_summary = ", ".join(
        f"{name}: {status}" for name, status in scanners.items()
    ) or "No scanner evidence recorded"
    description = (task.description or "No task description provided.").strip()[
        :2000]
    return "\n".join([
        "## Summary",
        "",
        description,
        "",
        "## Changed files",
        "",
        *file_lines,
        "",
        "## Validation",
        "",
        f"- Governed tests: {test_summary}",
        (
            "- Security findings: "
            f"{int(security.get('high') or 0)} high, "
            f"{int(security.get('medium') or 0)} medium, "
            f"{int(security.get('low') or 0)} low"
        ),
        f"- Security scanners: {scanner_summary}",
        "",
        "## Governance",
        "",
        f"- AutoDev task: `{task.id}`",
        f"- Workflow: `{task.workflow_id}`",
        f"- Agent: `{task.agent_id}`",
        f"- Requested by: `{task.created_by or 'unknown'}`",
        f"- Approved by: `{approved_by or 'unknown'}`",
    ])


async def complete_approval(task_id: str) -> None:
    with Session(engine) as session:
        task = session.get(Task, task_id)
        sandbox = session.exec(select(Sandbox).where(
            Sandbox.task_id == task_id)).first()
        if not task or not sandbox or not sandbox.host_workspace:
            raise RuntimeError("Task worktree is unavailable")
        workspace = Path(sandbox.host_workspace)
        await asyncio.to_thread(_git, workspace, ["add", "-A"])
        author_name = "Agentic SDLC Workbench"
        author_email = "workbench@local"
        if (
            (project := session.get(Project, task.project_id))
            and project.source_type == "github"
            and project.repository_url
        ):
            owner, _ = parse_github_url(project.repository_url)
            identity = github_credentials.commit_identity(
                project.organization_id,
                project.created_by,
                owner,
                project.connector_id,
            )
            if identity:
                author_name, author_email = identity
        commit_message = f"agent: {task.title}\n\nAutoDev-Task: {task.id}"
        if task.created_by:
            commit_message += f"\nAutoDev-Requester: {task.created_by}"
        commit = await asyncio.to_thread(
            _git,
            workspace,
            [
                "-c", f"user.name={author_name}",
                "-c", f"user.email={author_email}",
                "commit", "-m", commit_message,
            ],
        )
        if commit.returncode:
            raise RuntimeError(commit.stderr.strip() or "Commit failed")
        revision = (await asyncio.to_thread(_git, workspace, ["rev-parse", "HEAD"])).stdout.strip()
        await record_event(session, task_id, "git.commit", "Commit created", revision)
        await update_phase(session, task, TaskStatus.DONE, "Done", 100)
        await record_event(session, task_id, "task.completed", "Task completed", "Worktree and evidence are preserved")
        result = {"status": "DONE", "commit": revision,
                  "task_id": task_id, "workspace": str(workspace)}
        evidence_provider.write(task_id, "result", result)
        await cleanup_sandbox(session, task_id, "approved commit")


async def complete_publication(
    task_id: str,
    branch: str,
    create_pull_request: bool,
    approved_by: str | None = None,
) -> dict[str, Any]:
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise RuntimeError("Task is unavailable")
        project = session.get(Project, task.project_id)
        sandbox = session.exec(select(Sandbox).where(
            Sandbox.task_id == task_id)).first()
        if not project or not sandbox or not sandbox.host_workspace:
            raise RuntimeError("Task worktree is unavailable")
        validate_publication(project, create_pull_request)
        published = await publish_repository(project, Path(sandbox.host_workspace), branch)
        result: dict[str, Any] = {**published, "pull_request": None}
        await record_event(
            session, task_id, "git.push", "Branch published", branch,
            data={
                "branch": branch,
                "commit": published["commit"],
                "github_actor": published.get("github_actor"),
                "github_auth_method": published.get("github_auth_method"),
                "github_installation_id": published.get("github_installation_id"),
                "requested_by": task.created_by,
                "approved_by": approved_by,
            },
        )
        if create_pull_request:
            task_artifacts = {
                item.kind: item.content
                for item in session.exec(
                    select(TaskArtifact).where(TaskArtifact.task_id == task_id).order_by(
                        TaskArtifact.id
                    )
                ).all()
            }
            body = _pull_request_body(task, task_artifacts, approved_by)
            result["pull_request"] = await create_github_pull_request(
                project,
                branch,
                task.title,
                body,
            )
            await record_event(
                session,
                task_id,
                "pull_request.created",
                "Pull request created",
                str(result["pull_request"].get("url") or ""),
                data={
                    "branch": branch,
                    "github_actor": result["pull_request"].get("github_actor"),
                    "github_auth_method": result["pull_request"].get(
                        "github_auth_method"
                    ),
                    "github_installation_id": result["pull_request"].get(
                        "github_installation_id"
                    ),
                    "requested_by": task.created_by,
                    "approved_by": approved_by,
                },
            )
        await _save_artifact(session, task_id, "publication", result)
        return result
