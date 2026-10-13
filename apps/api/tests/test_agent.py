from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent_framework import AgentResponse, Content, Message
from copilot.rpc import PermissionDecisionApproveOnce, PermissionDecisionUserNotAvailable
from copilot.session_events import PermissionRequestCustomTool, PermissionRequestRead

from app import registry
from app.agent import (
    AgentRuntime,
    ToolRuntime,
    _classify,
    _copilot_permission_handler,
    _looks_taskless,
    _read_file_chunk,
    _search_repository_text,
)
from app.model_recovery import ModelRecoveryDecision
from app.prompts import compose_agent_instructions, render_prompt
from app.providers import Decision, GovernanceDecision
from app.runtime_supervision import (
    ActionDecision,
    ExecutionTier,
    SupervisionDeniedError,
)


def test_compose_agent_instructions_loads_only_locally_attached_skills(
        tmp_path, monkeypatch
):
    monkeypatch.setitem(registry.REGISTRIES, "skills", tmp_path)
    registry.save_definition(
        "skills",
        "research",
        """name: research
version: 1.0.0
description: Gather evidence before changing code.
instructions: |-
    Inspect the controlling code and cite evidence.
source:
    declared_allowed_tools: Bash(rm:*)
""",
    )

    composed = compose_agent_instructions({
        "instructions": "Use the research-plan-implement-review loop.",
        "skills": ["research"],
    })

    assert "## Agent instructions" in composed
    assert "## Skill: research" in composed
    assert "Inspect the controlling code" in composed
    assert "Bash(rm:*)" not in composed


@pytest.mark.parametrize(
    ("command", "capability"),
    [
        (["npm", "ci"], "dependency.install"),
        (["python3", "-m", "pip", "install", "-r",
         "requirements.txt"], "dependency.install"),
        (["uv", "sync"], "dependency.install"),
        (["go", "mod", "download"], "dependency.install"),
        (["cargo", "fetch"], "dependency.install"),
        (["dotnet", "restore"], "dependency.install"),
        (["go", "test", "./..."], "test.run"),
        (["cargo", "test"], "test.run"),
        (["python3", "-m", "pytest", "-q"], "test.run"),
        (["dotnet", "test"], "test.run"),
    ],
)
def test_cross_ecosystem_command_classification(command, capability):
    assert _classify(command) == capability


def test_coding_prompt_is_loaded_from_prompty():
    rendered = render_prompt(
        "coding-task", task_id="TASK-123", title="Inspect", description="Read files",
        steering_block="- Keep the API",
        session_context_block="Assistant: The repository is empty.\nUser: Draft a PRD.",
    )
    assert "Task TASK-123: Inspect" in rendered
    assert "Developer steering received" in rendered
    assert "Context from prior runs" in rendered
    assert "Assistant: The repository is empty." in rendered


def test_large_file_reads_are_paginated(tmp_path):
    path = tmp_path / "large.txt"
    path.write_text("0123456789" * 2000, encoding="utf-8")

    first = _read_file_chunk(path, "large.txt", limit=1000)
    second = _read_file_chunk(
        path, "large.txt", offset=first["next_offset"], limit=1000)

    assert len(first["content"]) == 1000
    assert first["truncated"] is True
    assert second["offset"] == 1000


def test_targeted_text_search_excludes_dependencies(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "gateway.ts").write_text("const securityBoundary = true;\n", encoding="utf-8")
    dependency = tmp_path / "node_modules" / "package"
    dependency.mkdir(parents=True)
    (dependency / "index.ts").write_text("securityBoundary\n", encoding="utf-8")

    result = _search_repository_text(
        tmp_path, tmp_path, "securityBoundary", pattern="**/*.ts")

    assert result["matches"] == [{
        "path": "src/gateway.ts", "line": 1, "text": "const securityBoundary = true;"
    }]


def test_text_search_accepts_file_path_and_clamps_match_limit(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "".join(f"Agent line {line}\n" for line in range(250)), encoding="utf-8")

    result = _search_repository_text(
        tmp_path, readme, "Agent", max_matches=1000
    )

    assert len(result["matches"]) == 200
    assert result["truncated"] is True
    assert result["files_scanned"] == 1


def test_taskless_response_detection():
    assert _looks_taskless(
        "I am ready to assist you. Please provide the task you would like me to perform."
    )


def test_copilot_permission_handler_only_dispatches_workbench_custom_tools():
    allowed = _copilot_permission_handler(
        PermissionRequestCustomTool(
            tool_description="Read a repository file", tool_name="read_file"
        ),
        {},
    )
    unknown = _copilot_permission_handler(
        PermissionRequestCustomTool(
            tool_description="Unknown custom tool", tool_name="untrusted_tool"
        ),
        {},
    )
    builtin = _copilot_permission_handler(
        PermissionRequestRead(
            path="README.md", intention="Inspect repository"), {},
    )

    assert isinstance(allowed, PermissionDecisionApproveOnce)
    assert isinstance(unknown, PermissionDecisionUserNotAvailable)
    assert isinstance(builtin, PermissionDecisionUserNotAvailable)


class FakeGovernance:
    def __init__(self, decision=Decision.ALLOW):
        self.decision = decision

    async def evaluate(self, agent_id, action, arguments, context):
        return GovernanceDecision(
            self.decision, agent_id, action, "test-policy", "1", "test decision"
        )


class FakeSupervisor:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.actions = []

    async def before_action(self, task_id, action, agent_id=None):
        self.actions.append((task_id, action))
        decision = ActionDecision(
            allowed=self.allowed,
            provider="test-supervisor",
            capability=action.capability,
            agent_tier=ExecutionTier.STANDARD,
            required_tier=ExecutionTier.STANDARD,
            reason="supervision allowed" if self.allowed else "supervision denied",
        )
        if not self.allowed:
            raise SupervisionDeniedError(decision)
        return decision


@pytest.mark.asyncio
async def test_tool_runtime_enforces_governance_and_records_events(tmp_path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    events = []

    async def callback(event_type, title, detail, severity, data):
        events.append((event_type, data))

    runtime = ToolRuntime(
        task_id="TASK-1", agent_id="did:local:developer", workspace=tmp_path,
        container_id="unused", callback=callback, sandbox=SimpleNamespace(),
        governance=FakeGovernance(), supervisor=FakeSupervisor(),
    )
    result = await runtime.execute("read_file", {"path": "README.md"})

    assert result["content"] == "hello"
    assert [event[0] for event in events] == [
        "tool.requested", "tool.allowed", "runtime_supervision.allowed", "tool.completed"
    ]


@pytest.mark.asyncio
async def test_tool_runtime_denies_before_file_write(tmp_path):
    async def callback(*args):
        return None

    runtime = ToolRuntime(
        task_id="TASK-1", agent_id="did:local:developer", workspace=tmp_path,
        container_id="unused", callback=callback, sandbox=SimpleNamespace(),
        governance=FakeGovernance(Decision.DENY), supervisor=FakeSupervisor(),
    )

    with pytest.raises(PermissionError, match="test decision"):
        await runtime.execute("write_file", {"path": "denied.txt", "content": "no"})
    assert not (tmp_path / "denied.txt").exists()


@pytest.mark.asyncio
async def test_tool_runtime_supervisor_denies_before_file_write(tmp_path):
    events = []

    async def callback(event_type, title, detail, severity, data):
        events.append(event_type)

    runtime = ToolRuntime(
        task_id="TASK-1", agent_id="did:local:developer", workspace=tmp_path,
        container_id="unused", callback=callback, sandbox=SimpleNamespace(),
        governance=FakeGovernance(), supervisor=FakeSupervisor(allowed=False),
    )

    with pytest.raises(PermissionError, match="supervision denied"):
        await runtime.execute("write_file", {"path": "denied.txt", "content": "no"})

    assert "runtime_supervision.denied" in events
    assert not (tmp_path / "denied.txt").exists()


@pytest.mark.asyncio
async def test_tool_runtime_records_unclassified_command_denial(tmp_path):
    events = []

    async def callback(event_type, title, detail, severity, data):
        events.append((event_type, data))

    runtime = ToolRuntime(
        task_id="TASK-1", agent_id="did:local:developer", workspace=tmp_path,
        container_id="unused", callback=callback, sandbox=SimpleNamespace(),
        governance=FakeGovernance(), supervisor=FakeSupervisor(),
    )

    with pytest.raises(ValueError, match="outside the governed"):
        await runtime.execute("run_command", {"arguments": ["bash", "-lc", "cat README.md"]})

    assert events[-1] == (
        "tool.denied",
        {"capability": None, "decision": "DENY",
         "arguments": {"arguments": ["bash", "-lc", "cat README.md"]}},
    )


@pytest.mark.asyncio
async def test_tool_runtime_uses_explicit_policy_invocation_budget(tmp_path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")

    async def callback(*args):
        return None

    runtime = ToolRuntime(
        task_id="TASK-1", agent_id="did:local:developer", workspace=tmp_path,
        container_id="unused", callback=callback, sandbox=SimpleNamespace(),
        governance=FakeGovernance(), supervisor=FakeSupervisor(), max_tool_invocations=2,
    )

    await runtime.execute("read_file", {"path": "README.md"})
    await runtime.execute("read_file", {"path": "README.md"})
    with pytest.raises(RuntimeError, match="policy limit of 2"):
        await runtime.execute("read_file", {"path": "README.md"})


class FakeAgent:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.options = []
        self.closed = False
        self.session = object()
        self.session_creations = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def create_session(self):
        self.session_creations += 1
        return self.session

    async def run(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.options.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return AgentResponse(
            messages=[Message(role="assistant", contents=[
                              Content.from_text(response)])],
            usage_details={"input_token_count": 4, "output_token_count": 2},
            additional_properties={"model": "resolved-model"},
        )


def _runtime_settings(**overrides):
    values = {
        "model_provider": "copilot",
        "model_fallback_provider": "ollama",
        "model_fallback_name": "local-model",
        "model_request_timeout_seconds": 300,
        "agent_turn_timeout_seconds": 1800,
        "model_recovery_timeout_seconds": 600,
        "max_agent_steps": 40,
        "copilot_home": ".copilot",
        "copilot_cli_path": "copilot",
        "ollama_url": "http://ollama:11434",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_agent_framework_session_receives_steering_and_runtime_context(tmp_path):
    fake = FakeAgent(["Initial answer", "Steering acknowledged"])
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.settings = _runtime_settings()
    runtime.sandbox = SimpleNamespace()
    runtime.governance = FakeGovernance()
    runtime.supervisor = FakeSupervisor()
    runtime._copilot_agent = lambda *args: fake
    steering_polls = 0

    async def steering():
        nonlocal steering_polls
        steering_polls += 1
        return ["Use the focused test"]

    events = []

    async def callback(event_type, title, detail, severity, data):
        events.append((event_type, detail, data))

    result = await runtime.run(
        task_id="TASK-STEER", title="Test steering", description="Inspect only",
        agent_id="did:local:developer", model_name="auto", task_mode="assessment",
        verbose_logging=False, workspace=tmp_path, container_id="unused",
        callback=callback, steering_provider=steering,
    )

    assert result == "Steering acknowledged"
    assert fake.prompts[1] == "Developer steering:\n- Use the focused test"
    assert "workbench_runtime" in fake.options[0]["function_invocation_kwargs"]
    tool_runtime = fake.options[0]["function_invocation_kwargs"]["workbench_runtime"]
    assert tool_runtime.max_tool_invocations == 500
    assert tool_runtime.max_shell_invocations == 100
    assert fake.closed is True
    completed = [event for event in events if event[0] == "model.completed"]
    assert completed[-1][2]["usage"]["input_tokens"] == 4


@pytest.mark.asyncio
async def test_operator_retry_reuses_agent_framework_session(tmp_path):
    agent = FakeAgent([RuntimeError("transient timeout"), "Recovered"])
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.settings = _runtime_settings()
    runtime.sandbox = SimpleNamespace()
    runtime.governance = FakeGovernance()
    runtime.supervisor = FakeSupervisor()
    runtime._copilot_agent = lambda *args: agent
    recoveries = []

    async def recover(model, error, attempt):
        recoveries.append((model, error, attempt))
        return ModelRecoveryDecision("retry")

    async def callback(*args):
        return None

    result = await runtime.run(
        task_id="TASK-RETRY", title="Retry", description="Inspect only",
        agent_id="did:local:developer", model_name="gpt-test", task_mode="assessment",
        verbose_logging=False, workspace=tmp_path, container_id="unused",
        callback=callback, model_recovery=recover,
    )

    assert result == "Recovered"
    assert recoveries == [("gpt-test", "transient timeout", 1)]
    assert agent.prompts[-1].startswith(
        "Continue from the last completed step")
    assert agent.session_creations == 1
    assert all(options["session"]
               is agent.session for options in agent.options)
    assert agent.closed is True


def test_copilot_agent_uses_workbench_timeout_and_disables_file_hooks(tmp_path):
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.settings = _runtime_settings()
    captured = {}

    def construct(**kwargs):
        captured.update(kwargs)
        return object()

    with patch("app.agent.runtime.GitHubCopilotAgent", side_effect=construct):
        runtime._copilot_agent("instructions", "auto", tmp_path)

    options = captured["default_options"]
    assert options["cli_path"] == "copilot"
    assert options["on_permission_request"] is _copilot_permission_handler
    assert options["timeout"] == 1800.0
    assert options["enable_file_hooks"] is False
    assert options["working_directory"] == str(tmp_path)
    assert "model" not in options
    assert captured["tools"]
