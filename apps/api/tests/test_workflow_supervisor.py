from pathlib import Path

import pytest

from app import registry
from app.models import TaskStatus
from app.workflow_supervisor import WorkflowSupervisor


WORKFLOW = Path(__file__).parents[3] / "workflows" / "sdlc.yaml"


@pytest.mark.asyncio
async def test_transitions_are_executed_as_hypervisor_saga_steps(monkeypatch, tmp_path):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    (tmp_path / "sdlc.yaml").write_text(WORKFLOW.read_text(encoding="utf-8"))
    supervisor = WorkflowSupervisor()

    intake = await supervisor.transition(
        "TASK-001", "did:local:developer", TaskStatus.INTAKE, 0
    )
    implementation = await supervisor.transition(
        "TASK-001", "did:local:developer", TaskStatus.IMPLEMENTATION, intake.progress
    )

    managed = supervisor.hypervisor.get_session(intake.session_id)
    assert managed is not None
    saga = managed.saga.get_saga(intake.saga_id)
    assert saga is not None
    assert intake.label == "Repository"
    assert implementation.progress == 35
    assert [step.state.value for step in saga.steps].count("committed") == 2


@pytest.mark.asyncio
async def test_inherited_progress_and_terminal_session_cleanup(monkeypatch, tmp_path):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    (tmp_path / "sdlc.yaml").write_text(WORKFLOW.read_text(encoding="utf-8"))
    supervisor = WorkflowSupervisor()

    recovery = await supervisor.transition(
        "TASK-002", "did:local:developer", TaskStatus.AWAITING_MODEL, 47
    )
    done = await supervisor.transition(
        "TASK-002", "did:local:developer", TaskStatus.DONE, recovery.progress
    )

    assert recovery.progress == 47
    assert done.progress == 100
    assert supervisor.hypervisor.get_session(done.session_id) is not None
    assert done.session_id not in supervisor.hypervisor._active_ids
