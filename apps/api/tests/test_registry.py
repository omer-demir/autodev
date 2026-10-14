import pytest
import yaml

from app import registry
from app.evaluation import set_agent_evaluation_requirement
from app.workflow_orchestration import workflow_owner_agent


def test_agent_yaml_cannot_self_promote(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
status: promoted
identity:
  id: did:local:candidate
capabilities: [repository.read]
"""

    saved = registry.save_definition("agents", "candidate", raw)

    assert saved["data"]["status"] == "draft"


def test_promotion_gate_can_mark_agent_promoted(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
status: promoted
identity:
  id: did:local:candidate
capabilities: [repository.read]
"""

    saved = registry.save_definition(
        "agents", "candidate", raw, allow_agent_promotion=True
    )

    assert saved["data"]["status"] == "promoted"


def test_agent_evaluation_bypass_is_explicit_and_attributed(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
status: draft
identity:
  id: did:local:candidate
capabilities: [repository.read]
"""
    registry.save_definition("agents", "candidate", raw)

    assert not registry.agent_can_execute(
        registry.get_definition("agents", "candidate")["data"]
    )
    updated = set_agent_evaluation_requirement(
        "candidate", False, "Temporary trial of imported agent", "admin-1"
    )

    assert updated["data"]["status"] == "draft"
    assert updated["data"]["evaluation_required"] is False
    assert updated["data"]["evaluation_override"]["approved_by"] == "admin-1"
    assert updated["data"]["evaluation_override"]["reason"] == (
        "Temporary trial of imported agent"
    )
    assert registry.agent_can_execute(updated["data"])

    restored = set_agent_evaluation_requirement(
        "candidate", True, "Trial complete", "admin-1"
    )
    assert restored["data"]["evaluation_required"] is True
    assert "evaluation_override" not in restored["data"]
    assert not registry.agent_can_execute(restored["data"])


def test_agent_evaluation_required_must_be_boolean(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
status: draft
evaluation_required: sometimes
identity:
  id: did:local:candidate
capabilities: [repository.read]
"""

    with pytest.raises(registry.RegistryError, match="must be true or false"):
        registry.save_definition("agents", "candidate", raw)


@pytest.mark.parametrize(
    ("model_yaml", "message"),
    [
        ("model: copilot", "must be a YAML object"),
        ("model:\n  provider: unknown\n  name: test", "provider must be"),
        ("model:\n  provider: copilot\n  name: ''", "name must be non-empty"),
    ],
)
def test_agent_model_preference_is_validated(
    tmp_path, monkeypatch, model_yaml, message
):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = f"""name: Candidate
version: 1.0.0
identity:
  id: did:local:candidate
capabilities: [repository.read]
{model_yaml}
"""

    with pytest.raises(registry.RegistryError, match=message):
        registry.save_definition("agents", "candidate", raw)


def test_agent_unknown_capability_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
identity:
  id: did:local:candidate
capabilities: [repository.read, imaginary.execute]
"""

    with pytest.raises(registry.RegistryError, match="imaginary.execute"):
        registry.save_definition("agents", "candidate", raw)


def test_policy_unknown_capability_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "policies", tmp_path)
    raw = """name: Invalid policy
version: '1.0'
default_action: deny
rules:
  - capabilities: [unknown.action]
    decision: allow
"""

    with pytest.raises(registry.RegistryError, match="unknown.action"):
        registry.save_definition("policies", "invalid", raw)


def test_evaluation_scenario_rejects_required_forbidden_overlap(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "evaluation-suites", tmp_path)
    raw = """name: Invalid suite
version: 1.0.0
scenarios:
  - id: invalid-overlap
    required_capabilities: [repository.write]
    forbidden_capabilities: [repository.write]
"""

    with pytest.raises(registry.RegistryError, match="both required and forbidden"):
        registry.save_definition("evaluation-suites", "invalid", raw)


def test_change_evaluation_requires_repository_write(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "evaluation-suites", tmp_path)
    raw = """name: Invalid suite
version: 1.0.0
scenarios:
  - id: invalid-change
    task_mode: change
    required_capabilities: [repository.read]
"""

    with pytest.raises(registry.RegistryError, match="must require repository.write"):
        registry.save_definition("evaluation-suites", "invalid", raw)


def test_active_workflows_have_a_write_capable_agent():
    agents = {
        definition["id"]: definition["data"]
        for definition in registry.list_definitions("agents")
    }

    for definition in registry.list_definitions("workflows"):
        workflow = definition["data"]
        if workflow.get("status") != "active":
            continue
        agent_ids = {
            str(stage["agent"]).removeprefix("did:local:")
            for stage in workflow.get("stages", [])
        }
        if default_agent := workflow.get("default_agent"):
            agent_ids.add(str(default_agent).removeprefix("did:local:"))
        assert any(
            "repository.write" in agents[agent_id].get("capabilities", [])
            for agent_id in agent_ids
        ), f"Active workflow {definition['id']} has no write-capable agent"


def test_active_workflow_agents_can_execute():
    agents = {
        definition["id"]: definition["data"]
        for definition in registry.list_definitions("agents")
    }

    for definition in registry.list_definitions("workflows"):
        workflow = definition["data"]
        if workflow.get("status") != "active":
            continue
        agent_ids = {
            str(stage["agent"]).removeprefix("did:local:")
            for stage in workflow.get("stages", [])
        }
        if default_agent := workflow.get("default_agent"):
            agent_ids.add(str(default_agent).removeprefix("did:local:"))
        blocked_agents = sorted(
            agent_id
            for agent_id in agent_ids
            if not registry.agent_can_execute(agents[agent_id])
        )
        assert not blocked_agents, (
            f"Active workflow {definition['id']} has blocked agents: "
            f"{', '.join(blocked_agents)}"
        )


@pytest.mark.parametrize(
    ("workflow_id", "implementer", "stage_prefix"),
    [
        ("backend-implementation", "did:local:backend-implementer", "backend"),
        ("ui-implementation", "did:local:frontend-implementer", "ui"),
        (
            "infrastructure-implementation",
            "did:local:infrastructure-implementer",
            "infrastructure",
        ),
    ],
)
def test_specialist_implementation_workflows_are_independently_runnable(
    workflow_id, implementer, stage_prefix
):
    workflow = registry.get_definition("workflows", workflow_id)["data"]
    stages = workflow["stages"]
    agent_definitions = {
        f"did:local:{definition['id']}": definition["data"]
        for definition in registry.list_definitions("agents")
    }

    assert workflow["status"] == "active"
    assert workflow["default_mode"] == "change"
    assert workflow["orchestration"] == {
        "mode": "sequential",
        "max_parallel": 1,
    }
    assert stages[0]["id"] == f"{stage_prefix}-implementation"
    assert stages[0]["agent"] == implementer
    assert stages[0]["inputs"] == ["request", "messages", "workspace"]
    assert stages[1]["agent"] == "did:local:tester"
    assert stages[2]["agent"] == implementer
    assert stages[3]["agent"] == "did:local:delivery-reviewer"
    assert workflow_owner_agent(
        workflow, agent_definitions, "did:local:developer"
    ) == implementer


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("default_mode", "sometimes", "default_mode must be change or assessment"),
        ("default_agent", "architect", "default_agent must be a local agent DID"),
    ],
)
def test_workflow_defaults_are_validated(tmp_path, monkeypatch, field, value, message):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    raw = yaml.safe_dump({
        "name": "Invalid defaults",
        "version": "1.0.0",
        field: value,
        "phases": [
            {"id": "done", "status": "DONE", "label": "Done", "progress": 100},
        ],
    }, sort_keys=False)

    with pytest.raises(registry.RegistryError, match=message):
        registry.save_definition("workflows", "invalid-defaults", raw)


def test_multi_agent_dag_workflow_is_validated(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    raw = yaml.safe_dump({
        "name": "Delivery",
        "version": "1.0.0",
        "phases": [
            {"id": "planning", "status": "PLANNING",
                "label": "Planning", "progress": 20},
            {"id": "done", "status": "DONE", "label": "Done", "progress": 100},
        ],
        "orchestration": {"mode": "dag", "max_parallel": 2},
        "stages": [
            {
                "id": "research",
                "agent": "did:local:researcher",
                "responsibility": "Gather grounded context.",
                "inputs": ["request", "workspace"],
                "outputs": ["research"],
                "handoff": {"include": ["summary", "artifacts", "workspace"]},
            },
            {
                "id": "design",
                "agent": "did:local:designer",
                "responsibility": "Design the experience and technical approach.",
                "depends_on": ["research"],
                "inputs": ["request", "research"],
                "outputs": ["design"],
            },
        ],
    }, sort_keys=False)

    saved = registry.save_definition("workflows", "delivery", raw)

    assert saved["data"]["orchestration"] == {"mode": "dag", "max_parallel": 2}
    assert saved["data"]["stages"][1]["depends_on"] == ["research"]


def test_workflow_dependency_cycle_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    raw = yaml.safe_dump({
        "name": "Cyclic",
        "version": "1.0.0",
        "phases": [
            {"id": "planning", "status": "PLANNING",
                "label": "Planning", "progress": 20},
        ],
        "orchestration": {"mode": "dag", "max_parallel": 2},
        "stages": [
            {
                "id": "first",
                "agent": "did:local:researcher",
                "responsibility": "First stage.",
                "depends_on": ["second"],
                "inputs": ["request"],
                "outputs": ["first-output"],
            },
            {
                "id": "second",
                "agent": "did:local:designer",
                "responsibility": "Second stage.",
                "depends_on": ["first"],
                "inputs": ["first-output"],
                "outputs": ["second-output"],
            },
        ],
    }, sort_keys=False)

    with pytest.raises(registry.RegistryError, match="must not contain cycles"):
        registry.save_definition("workflows", "cyclic", raw)


def test_dag_artifact_input_requires_dependency_ancestor(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "workflows", tmp_path)
    raw = yaml.safe_dump({
        "name": "Unrelated input",
        "version": "1.0.0",
        "phases": [
            {"id": "planning", "status": "PLANNING",
                "label": "Planning", "progress": 20},
        ],
        "orchestration": {"mode": "dag", "max_parallel": 2},
        "stages": [
            {
                "id": "research",
                "agent": "did:local:researcher",
                "responsibility": "Research.",
                "inputs": ["request"],
                "outputs": ["research-output"],
            },
            {
                "id": "design",
                "agent": "did:local:designer",
                "responsibility": "Design.",
                "inputs": ["request", "research-output"],
                "outputs": ["design-output"],
            },
        ],
    }, sort_keys=False)

    with pytest.raises(registry.RegistryError, match="not produced by a dependency ancestor"):
        registry.save_definition("workflows", "unrelated-input", raw)
