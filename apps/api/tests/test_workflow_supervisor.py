from pathlib import Path

import pytest

from app import registry
from app.models import TaskStatus
from app.runtime_supervision import ActionSpec, LocalRuntimeSupervisor
from app.workflow_supervisor import WorkflowSupervisor


WORKFLOW = Path(__file__).parents[3] / "workflows" / "sdlc.yaml"


class RecordingSupervisor(LocalRuntimeSupervisor):
    def __init__(self):
        super().__init__()
        self.starts = []
        self.transitions = []
        self.terminations = []

    async def start(self, **kwargs):
        self.starts.append((kwargs["task_id"], kwargs["agent_id"]))
        return await super().start(**kwargs)

    async def transition(self, handle, *, phase_id):
        self.transitions.append((handle.session_id, phase_id))
        return await super().transition(handle, phase_id=phase_id)

    async def terminate(self, handle, *, reason):
        self.terminations.append((handle.session_id, reason))
        return await super().terminate(handle, reason=reason)


@pytest.mark.asyncio
async def test_transitions_are_executed_through_provider_contract(monkeypatch, tmp_path):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    (tmp_path / "sdlc.yaml").write_text(WORKFLOW.read_text(encoding="utf-8"))
    provider = RecordingSupervisor()
    supervisor = WorkflowSupervisor(provider)

    intake = await supervisor.transition(
        "TASK-001", "did:local:developer", TaskStatus.INTAKE, 0
    )
    implementation = await supervisor.transition(
        "TASK-001", "did:local:developer", TaskStatus.IMPLEMENTATION, intake.progress
    )

    assert intake.label == "Repository"
    assert implementation.progress == 35
    assert provider.transitions == [
        (intake.session_id, "intake"),
        (intake.session_id, "implementation"),
    ]
    assert implementation.supervision["provider"] == "local"


@pytest.mark.asyncio
async def test_inherited_progress_and_terminal_session_cleanup(monkeypatch, tmp_path):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    (tmp_path / "sdlc.yaml").write_text(WORKFLOW.read_text(encoding="utf-8"))
    provider = RecordingSupervisor()
    supervisor = WorkflowSupervisor(provider)

    recovery = await supervisor.transition(
        "TASK-002", "did:local:developer", TaskStatus.AWAITING_MODEL, 47
    )
    done = await supervisor.transition(
        "TASK-002", "did:local:developer", TaskStatus.DONE, recovery.progress
    )

    assert recovery.progress == 47
    assert done.progress == 100
    assert provider.terminations == [(done.session_id, "done")]
    assert done.supervision["termination"]["provider"] == "local"
    assert "TASK-002" not in supervisor._tasks


@pytest.mark.asyncio
async def test_stage_agent_receives_distinct_supervision_handle(monkeypatch, tmp_path):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    (tmp_path / "sdlc.yaml").write_text(WORKFLOW.read_text(encoding="utf-8"))
    provider = RecordingSupervisor()
    supervisor = WorkflowSupervisor(provider)
    await supervisor.transition(
        "TASK-003", "did:local:developer", TaskStatus.INTAKE, 0
    )

    await supervisor.before_action(
        "TASK-003",
        ActionSpec(capability="repository.read", read_only=True),
        agent_id="did:local:reviewer",
    )
    await supervisor.transition(
        "TASK-003", "did:local:developer", TaskStatus.DONE, 5
    )

    assert provider.starts == [
        ("TASK-003", "did:local:developer"),
        ("TASK-003:did:local:reviewer", "did:local:reviewer"),
    ]
    assert len(provider.terminations) == 2
    assert not supervisor._agent_tasks
