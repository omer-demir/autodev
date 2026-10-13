import pytest

from app.workflow_orchestration import (
    WorkflowOrchestrationError,
    assert_parallel_stages_are_read_only,
    stage_artifact_inputs,
    stage_waves,
    workflow_owner_agent,
)


def test_dag_stages_form_parallel_dependency_waves():
    workflow = {
        "orchestration": {"mode": "dag", "max_parallel": 2},
        "stages": [
            {"id": "research", "agent": "did:local:researcher"},
            {"id": "ux", "agent": "did:local:designer",
                "depends_on": ["research"]},
            {"id": "architecture", "agent": "did:local:architect",
                "depends_on": ["research"]},
            {"id": "synthesis", "agent": "did:local:planner",
                "depends_on": ["ux", "architecture"]},
        ],
    }

    waves = stage_waves(workflow)

    assert [[stage["id"] for stage in wave] for wave in waves] == [
        ["research"], ["ux", "architecture"], ["synthesis"]
    ]


def test_parallel_write_capable_agents_are_rejected():
    waves = [[
        {"id": "frontend", "agent": "did:local:implementer"},
        {"id": "backend", "agent": "did:local:reviewer"},
    ]]
    definitions = {
        "did:local:implementer": {"capabilities": ["repository.read", "repository.write"]},
        "did:local:reviewer": {"capabilities": ["repository.read"]},
    }

    with pytest.raises(WorkflowOrchestrationError, match="write-capable agent"):
        assert_parallel_stages_are_read_only(waves, definitions)


def test_write_capable_stage_owns_workflow_governance():
    workflow = {
        "stages": [
            {"agent": "did:local:researcher"},
            {"agent": "did:local:architect"},
            {"agent": "did:local:reviewer"},
        ],
    }
    definitions = {
        "did:local:researcher": {"capabilities": ["repository.read"]},
        "did:local:architect": {
            "capabilities": ["repository.read", "repository.write"]
        },
        "did:local:reviewer": {"capabilities": ["repository.read"]},
    }

    assert workflow_owner_agent(
        workflow, definitions, "did:local:developer"
    ) == "did:local:architect"


def test_stage_receives_only_declared_artifacts():
    artifacts = {
        "research": {"summary": "evidence"},
        "design": {"summary": "guide"},
    }

    selected = stage_artifact_inputs(
        {"inputs": ["request", "research"]}, artifacts
    )

    assert selected == {"research": {"summary": "evidence"}}


def test_stage_rejects_missing_declared_artifact():
    with pytest.raises(WorkflowOrchestrationError, match="missing required artifacts: design"):
        stage_artifact_inputs(
            {"id": "planning", "inputs": ["request", "design"]},
            {"research": {"summary": "evidence"}},
        )
