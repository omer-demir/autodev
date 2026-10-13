import shutil
from pathlib import Path
from typing import Any

from sqlmodel import Session

from .agent import ToolRuntime
from .config import get_settings
from .database import engine
from .models import Task, TaskStatus
from .providers import get_governance_provider, get_sandbox_provider
from .registry import get_definition
from .workflow import record_event
from .workflow_supervisor import workflow_supervisor
from .workspace_snapshots import workspace_snapshots


async def run_governed_tool(
    job_id: str,
    task_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise RuntimeError(f"Task not found: {task_id}")
        organization_id = task.organization_id
        agent_id = task.agent_id

    root = Path(get_settings().workspace_dir) / "remote-tools" / job_id
    workspace = root / "repo"
    revision = await workspace_snapshots.restore_latest(task_id, workspace)
    if not revision:
        raise RuntimeError(
            "The session has no workspace revision; run the task before invoking tools"
        )

    definition = get_definition(
        "agents", agent_id.removeprefix("did:local:")
    )["data"]
    environment = definition.get("environment", {})
    sandbox = get_sandbox_provider()
    created: dict[str, Any] | None = None
    supervision_id = f"{task_id}:{job_id}"
    supervision_started = False
    succeeded = False

    async def callback(
        event_type: str,
        title: str,
        detail: str,
        severity: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        with Session(engine) as session:
            await record_event(
                session,
                task_id,
                event_type,
                title,
                detail,
                severity,
                data,
            )

    try:
        await workflow_supervisor.transition(
            supervision_id,
            agent_id,
            TaskStatus.IMPLEMENTATION,
            0,
        )
        supervision_started = True
        created = await sandbox.create({
            "name": f"autodev-tool-{job_id.lower()}",
            "workspace": str(workspace),
            "image": environment.get("image"),
            "network_mode": environment.get("network_mode", "none"),
            "workspace_access": environment.get("workspace_access", "read-write"),
            "pool_profile": environment.get(
                "pool_profile", get_settings().azure_session_pool_profile
            ),
            "environment": environment.get("variables", {}),
        })
        runtime = ToolRuntime(
            task_id=supervision_id,
            agent_id=agent_id,
            workspace=workspace,
            container_id=str(created["container_id"]),
            callback=callback,
            sandbox=sandbox,
            governance=get_governance_provider(),
            supervisor=workflow_supervisor,
        )
        result = await runtime.execute(tool_name, arguments)
        checkpoint = await workspace_snapshots.checkpoint(
            task_id,
            organization_id,
            workspace,
            revision.id,
        )
        result["workspace_revision_id"] = checkpoint.id
        succeeded = True
        return result
    finally:
        try:
            if supervision_started:
                await workflow_supervisor.transition(
                    supervision_id,
                    agent_id,
                    TaskStatus.DONE if succeeded else TaskStatus.FAILED,
                    100 if succeeded else 0,
                )
        finally:
            try:
                if created:
                    await sandbox.kill(str(created["container_id"]))
            finally:
                shutil.rmtree(root, ignore_errors=True)
