import re
from pathlib import Path
from typing import Any

import yaml

from .capabilities import SUPPORTED_CAPABILITIES, SUPPORTED_CAPABILITY_RESOLVERS
from .evaluation_terms import term_alternatives


class RegistryError(ValueError):
    pass


ROOT = Path(__file__).resolve().parents[3]
REGISTRIES = {
    "agents": ROOT / "agents",
    "mcp": ROOT / "mcp" / "servers",
    "workflows": ROOT / "workflows",
    "policies": ROOT / "policies",
    "evaluation-suites": ROOT / "evaluations" / "suites",
    "harnesses": ROOT / "harnesses",
    "capability-catalogs": ROOT / "capability-catalogs",
    "skills": ROOT / "skills",
}
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
WORKFLOW_STATUSES = {
    "INTAKE", "PLANNING", "IMPLEMENTATION", "AWAITING_MODEL", "TESTING",
    "SECURITY", "REVIEW", "AWAITING_APPROVAL", "DONE", "FAILED", "CANCELLED",
}
WORKFLOW_CONTEXT_INPUTS = {"request", "messages", "workspace"}


def _directory(kind: str) -> Path:
    try:
        directory = REGISTRIES[kind]
    except KeyError as exc:
        raise RegistryError(f"Unknown registry: {kind}") from exc
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _path(kind: str, identifier: str) -> Path:
    if not IDENTIFIER.fullmatch(identifier):
        raise RegistryError(
            "Definition ID must contain only lowercase letters, numbers, '.', '-' or '_'")
    return _directory(kind) / f"{identifier}.yaml"


def _validate(kind: str, identifier: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RegistryError("Definition must be a YAML object")
    required = {
        "agents": ("name", "identity", "version"),
        "mcp": ("name", "transport", "version"),
        "workflows": ("name", "version", "phases"),
        "policies": ("name", "version", "default_action", "rules"),
        "evaluation-suites": ("name", "version", "scenarios"),
        "harnesses": ("name", "version", "capability_catalog", "tools"),
        "capability-catalogs": ("name", "version", "capabilities"),
        "skills": ("name", "version", "description", "instructions"),
    }[kind]
    missing = [field for field in required if field not in data]
    if missing:
        raise RegistryError(f"Missing required fields: {', '.join(missing)}")
    if kind == "agents" and data.get("identity", {}).get("id") != f"did:local:{identifier}":
        raise RegistryError(
            f"Agent identity.id must be did:local:{identifier}")
    if kind == "agents":
        evaluation_required = data.get("evaluation_required", True)
        if not isinstance(evaluation_required, bool):
            raise RegistryError(
                "Agent evaluation_required must be true or false")
        declared = set()
        for field in ("capabilities", "approval", "deny"):
            values = data.get(field, [])
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                raise RegistryError(
                    f"Agent {field} must be a list of capabilities")
            declared.update(values)
        unknown = declared - SUPPORTED_CAPABILITIES
        if unknown:
            raise RegistryError(
                f"Unsupported agent capabilities: {', '.join(sorted(unknown))}")
        evaluation_suite = data.get("evaluation_suite")
        if evaluation_suite is not None and (
            not isinstance(evaluation_suite, str)
            or not IDENTIFIER.fullmatch(evaluation_suite)
        ):
            raise RegistryError(
                "Agent evaluation_suite must be a valid definition ID")
        model = data.get("model")
        if model is not None:
            if not isinstance(model, dict):
                raise RegistryError("Agent model must be a YAML object")
            provider = model.get("provider")
            name = model.get("name")
            if provider not in {"copilot", "ollama", "foundry"}:
                raise RegistryError(
                    "Agent model provider must be copilot, ollama, or foundry"
                )
            if not isinstance(name, str) or not name.strip():
                raise RegistryError("Agent model name must be non-empty text")
    if kind == "agents" and "environment" in data:
        environment = data["environment"]
        if not isinstance(environment, dict):
            raise RegistryError("Agent environment must be a YAML object")
        image = environment.get("image")
        if image is not None and (
            not isinstance(image, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}", image)
        ):
            raise RegistryError(
                "Agent environment.image must be a valid container image reference")
        instructions = environment.get("setup_instructions")
        if instructions is not None and not isinstance(instructions, str):
            raise RegistryError(
                "Agent environment.setup_instructions must be text")
    if kind == "mcp" and data.get("transport") not in {"stdio", "http", "sse"}:
        raise RegistryError("MCP transport must be stdio, http, or sse")
    if kind == "harnesses":
        tools = data.get("tools")
        if not isinstance(tools, list) or any(
            not isinstance(item, dict)
            or not item.get("name")
            or not item.get("description")
            or not isinstance(item.get("input_schema"), dict)
            or not (item.get("capability") or item.get("capability_resolver"))
            for item in tools
        ):
            raise RegistryError(
                "Harness tools require schemas and capability bindings")
        names = [str(item["name"]) for item in tools]
        if len(names) != len(set(names)):
            raise RegistryError("Harness tool names must be unique")
        unknown = {
            str(item["capability"])
            for item in tools if item.get("capability") not in {None, ""}
        } - SUPPORTED_CAPABILITIES
        if unknown:
            raise RegistryError(
                f"Unsupported harness capabilities: {', '.join(sorted(unknown))}")
        resolvers = {
            str(item["capability_resolver"])
            for item in tools if item.get("capability_resolver") not in {None, ""}
        }
        unknown_resolvers = resolvers - SUPPORTED_CAPABILITY_RESOLVERS
        if unknown_resolvers:
            raise RegistryError(
                f"Unsupported capability resolvers: {', '.join(sorted(unknown_resolvers))}")
    if kind == "capability-catalogs":
        entries = data.get("capabilities")
        if not isinstance(entries, list):
            raise RegistryError(
                "Capability catalog capabilities must be a list")
        if any(not isinstance(item, dict) or not item.get("action") for item in entries):
            raise RegistryError("Capability catalog entries require an action")
        unknown = {str(item["action"])
                   for item in entries} - SUPPORTED_CAPABILITIES
        if unknown:
            raise RegistryError(
                f"Unsupported catalog capabilities: {', '.join(sorted(unknown))}")
        expected = {str(item.get("expected", "")) for item in entries}
        if not expected <= {"ALLOW", "DENY", "REQUIRE_APPROVAL"}:
            raise RegistryError(
                "Capability expected decisions must be ALLOW, DENY, or REQUIRE_APPROVAL")
    if kind == "skills":
        if not isinstance(data.get("instructions"), str) or not data["instructions"].strip():
            raise RegistryError("Skill instructions must be non-empty text")
        if len(data["instructions"]) > 100_000:
            raise RegistryError("Skill instructions exceed 100000 characters")
    if kind == "agents" and "skills" in data and (
        not isinstance(data["skills"], list)
        or any(not isinstance(item, str) or not IDENTIFIER.fullmatch(item) for item in data["skills"])
    ):
        raise RegistryError("Agent skills must be a list of valid skill IDs")
    if kind == "policies":
        if data.get("default_action") not in {"allow", "deny", "require_approval"}:
            raise RegistryError(
                "Policy default_action must be allow, deny, or require_approval")
        if not isinstance(data.get("rules"), list):
            raise RegistryError("Policy rules must be a YAML list")
        for rule in data["rules"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("capabilities"), list):
                raise RegistryError(
                    "Each policy rule must contain a capabilities list")
            if rule.get("decision") not in {"allow", "deny", "require_approval"}:
                raise RegistryError(
                    "Policy rule decision must be allow, deny, or require_approval")
            unknown = set(rule["capabilities"]) - SUPPORTED_CAPABILITIES
            if unknown:
                raise RegistryError(
                    f"Unsupported policy capabilities: {', '.join(sorted(unknown))}")
    if kind in {"workflows", "evaluation-suites"} and not isinstance(
        data.get("phases" if kind == "workflows" else "scenarios"), list
    ):
        raise RegistryError("Phases and scenarios must be YAML lists")
    if kind == "evaluation-suites":
        intended_agent = data.get("agent")
        if intended_agent is not None and (
            not isinstance(intended_agent, str) or not IDENTIFIER.fullmatch(
                intended_agent)
        ):
            raise RegistryError(
                "Evaluation suite agent must be a valid agent ID")
        defaults = data.get("defaults") or {}
        if not isinstance(defaults, dict):
            raise RegistryError(
                "Evaluation suite defaults must be a YAML object")
        default_dataset = data.get("default_dataset") or {}
        if not isinstance(default_dataset, dict):
            raise RegistryError(
                "Evaluation suite default_dataset must be a YAML object")
        if default_dataset:
            version = default_dataset.get("version")
            status = default_dataset.get("status")
            reviewer = default_dataset.get("reviewed_by")
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise RegistryError(
                    "Evaluation suite default_dataset.version must be a positive integer")
            if status not in {"DRAFT", "REVIEWED", "FROZEN"}:
                raise RegistryError(
                    "Evaluation suite default_dataset.status must be DRAFT, REVIEWED, or FROZEN")
            if status in {"REVIEWED", "FROZEN"} and (
                not isinstance(reviewer, str) or not reviewer.strip()
            ):
                raise RegistryError(
                    "Reviewed or frozen default datasets require reviewed_by")
        scenario_ids: set[str] = set()
        for scenario in data["scenarios"]:
            if not isinstance(scenario, dict):
                raise RegistryError(
                    "Evaluation suite scenarios must be YAML objects")
            scenario_id = scenario.get("id")
            if not isinstance(scenario_id, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9-]{0,79}", scenario_id
            ):
                raise RegistryError(
                    "Evaluation scenarios require safe lowercase IDs")
            if scenario_id in scenario_ids:
                raise RegistryError("Evaluation scenario IDs must be unique")
            scenario_ids.add(scenario_id)
            required_capabilities = set(scenario.get(
                "required_capabilities", defaults.get(
                    "required_capabilities", [])
            ))
            forbidden_capabilities = set(scenario.get(
                "forbidden_capabilities", defaults.get(
                    "forbidden_capabilities", [])
            ))
            overlap = required_capabilities & forbidden_capabilities
            if overlap:
                raise RegistryError(
                    "Evaluation capabilities cannot be both required and forbidden: "
                    + ", ".join(sorted(overlap))
                )
            declared = required_capabilities | forbidden_capabilities
            unknown = declared - SUPPORTED_CAPABILITIES
            if unknown:
                raise RegistryError(
                    f"Unsupported evaluation capabilities: {', '.join(sorted(unknown))}")
            task_mode = scenario.get("task_mode", defaults.get("task_mode"))
            if task_mode not in {None, "change", "assessment"}:
                raise RegistryError(
                    "Evaluation scenario task_mode must be change or assessment"
                )
            if task_mode == "change" and "repository.write" not in required_capabilities:
                raise RegistryError(
                    "Change evaluation scenarios must require repository.write"
                )
            terms = (scenario.get("checks") or {}).get(
                "required_output_terms", [])
            if not isinstance(terms, list):
                raise RegistryError(
                    "Evaluation required_output_terms must be a list")
            for term in terms:
                try:
                    term_alternatives(term)
                except ValueError:
                    raise RegistryError(
                        "Each required output term must be text or a list of alternative phrases"
                    ) from None
    if kind == "workflows":
        default_mode = data.get("default_mode", "change")
        if default_mode not in {"change", "assessment"}:
            raise RegistryError(
                "Workflow default_mode must be change or assessment")
        default_agent = data.get("default_agent")
        if default_agent is not None and (
            not isinstance(default_agent, str)
            or not default_agent.startswith("did:local:")
            or not IDENTIFIER.fullmatch(default_agent.removeprefix("did:local:"))
        ):
            raise RegistryError(
                "Workflow default_agent must be a local agent DID")
        phase_ids: set[str] = set()
        phase_statuses: set[str] = set()
        for phase in data["phases"]:
            if not isinstance(phase, dict):
                raise RegistryError(
                    "Each workflow phase must be a YAML object")
            if not all(field in phase for field in ("id", "status", "label", "progress")):
                raise RegistryError(
                    "Each workflow phase requires id, status, label, and progress"
                )
            if not isinstance(phase["id"], str) or not IDENTIFIER.fullmatch(phase["id"]):
                raise RegistryError(
                    "Workflow phase IDs must be valid definition IDs")
            if phase["id"] in phase_ids or phase["status"] in phase_statuses:
                raise RegistryError(
                    "Workflow phase IDs and statuses must be unique")
            if phase["status"] not in WORKFLOW_STATUSES:
                raise RegistryError(
                    f"Unsupported workflow status: {phase['status']}")
            if not isinstance(phase["label"], str) or not phase["label"].strip():
                raise RegistryError(
                    "Workflow phase labels must be non-empty text")
            progress = phase["progress"]
            if progress != "inherit" and (
                not isinstance(progress, int) or isinstance(
                    progress, bool) or not 0 <= progress <= 100
            ):
                raise RegistryError(
                    "Workflow phase progress must be 0-100 or inherit")
            phase_ids.add(phase["id"])
            phase_statuses.add(phase["status"])
        orchestration = data.get("orchestration")
        stages = data.get("stages")
        if orchestration is not None or stages is not None:
            if not isinstance(orchestration, dict):
                raise RegistryError(
                    "Workflow orchestration must be a YAML object")
            mode = orchestration.get("mode")
            if mode not in {"sequential", "dag"}:
                raise RegistryError(
                    "Workflow orchestration mode must be sequential or dag")
            max_parallel = orchestration.get("max_parallel", 1)
            if (
                not isinstance(max_parallel, int)
                or isinstance(max_parallel, bool)
                or not 1 <= max_parallel <= 16
            ):
                raise RegistryError(
                    "Workflow max_parallel must be an integer from 1 to 16")
            if not isinstance(stages, list) or not stages:
                raise RegistryError(
                    "Executable workflows require at least one stage")
            stage_ids: set[str] = set()
            dependencies: dict[str, list[str]] = {}
            output_ids: set[str] = set()
            output_producers: dict[str, str] = {}
            for stage in stages:
                if not isinstance(stage, dict):
                    raise RegistryError(
                        "Each workflow stage must be a YAML object")
                required_stage_fields = (
                    "id", "agent", "responsibility", "inputs", "outputs")
                if not all(field in stage for field in required_stage_fields):
                    raise RegistryError(
                        "Each workflow stage requires id, agent, responsibility, inputs, and outputs"
                    )
                stage_id = stage["id"]
                if not isinstance(stage_id, str) or not IDENTIFIER.fullmatch(stage_id):
                    raise RegistryError(
                        "Workflow stage IDs must be valid definition IDs")
                if stage_id in stage_ids:
                    raise RegistryError("Workflow stage IDs must be unique")
                agent = stage["agent"]
                if not isinstance(agent, str) or not agent.startswith("did:local:") or not IDENTIFIER.fullmatch(agent.removeprefix("did:local:")):
                    raise RegistryError(
                        "Workflow stage agents must be local agent DIDs")
                if not isinstance(stage["responsibility"], str) or not stage["responsibility"].strip():
                    raise RegistryError(
                        "Workflow stage responsibility must be non-empty text")
                inputs = stage["inputs"]
                outputs = stage["outputs"]
                depends_on = stage.get("depends_on", [])
                if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
                    raise RegistryError(
                        "Workflow stage inputs must be a list of context or artifact IDs")
                if not isinstance(outputs, list) or not outputs or any(
                    not isinstance(item, str) or not IDENTIFIER.fullmatch(item) for item in outputs
                ):
                    raise RegistryError(
                        "Workflow stage outputs must be valid artifact IDs")
                if output_ids.intersection(outputs):
                    raise RegistryError(
                        "Workflow stage output IDs must be unique")
                if not isinstance(depends_on, list) or any(not isinstance(item, str) for item in depends_on):
                    raise RegistryError(
                        "Workflow stage depends_on must be a list of stage IDs")
                handoff = stage.get("handoff", {})
                if not isinstance(handoff, dict):
                    raise RegistryError(
                        "Workflow stage handoff must be a YAML object")
                include = handoff.get("include", ["summary", "artifacts"])
                if not isinstance(include, list) or any(
                    item not in {"summary", "artifacts", "messages", "workspace"} for item in include
                ):
                    raise RegistryError(
                        "Workflow handoff include values are unsupported")
                stage_ids.add(stage_id)
                dependencies[stage_id] = depends_on
                output_ids.update(outputs)
                output_producers.update(
                    {output_id: stage_id for output_id in outputs})
            for stage_id, stage_dependencies in dependencies.items():
                unknown = set(stage_dependencies) - stage_ids
                if unknown:
                    raise RegistryError(
                        f"Workflow stage {stage_id} depends on unknown stages: {', '.join(sorted(unknown))}"
                    )
                if stage_id in stage_dependencies:
                    raise RegistryError(
                        f"Workflow stage {stage_id} cannot depend on itself")
            visiting: set[str] = set()
            visited: set[str] = set()

            def visit(stage_id: str) -> None:
                if stage_id in visiting:
                    raise RegistryError(
                        "Workflow stage dependencies must not contain cycles")
                if stage_id in visited:
                    return
                visiting.add(stage_id)
                for dependency in dependencies[stage_id]:
                    visit(dependency)
                visiting.remove(stage_id)
                visited.add(stage_id)

            for stage_id in stage_ids:
                visit(stage_id)
            if mode == "sequential" and any(dependencies.values()):
                raise RegistryError(
                    "Sequential workflows use stage order and must omit depends_on")
            stage_order = [str(stage["id"]) for stage in stages]

            def ancestors(stage_id: str) -> set[str]:
                direct = set(dependencies[stage_id])
                result = set(direct)
                for dependency in direct:
                    result.update(ancestors(dependency))
                return result

            for index, stage in enumerate(stages):
                stage_id = str(stage["id"])
                available_stages = (
                    set(stage_order[:index])
                    if mode == "sequential"
                    else ancestors(stage_id)
                )
                for input_id in stage["inputs"]:
                    if input_id in WORKFLOW_CONTEXT_INPUTS:
                        continue
                    producer = output_producers.get(input_id)
                    if producer is None:
                        raise RegistryError(
                            f"Workflow stage {stage_id} has unknown artifact input: {input_id}"
                        )
                    if producer not in available_stages:
                        raise RegistryError(
                            f"Workflow stage {stage_id} input {input_id} is not produced by a dependency ancestor"
                        )
    return data


def list_definitions(kind: str) -> list[dict[str, Any]]:
    return [get_definition(kind, path.stem) for path in sorted(_directory(kind).glob("*.yaml"))]


def agent_can_execute(definition: dict[str, Any]) -> bool:
    return (
        definition.get("status") == "promoted"
        or definition.get("evaluation_required", True) is False
    )


def get_definition(kind: str, identifier: str) -> dict[str, Any]:
    path = _path(kind, identifier)
    if not path.exists():
        raise RegistryError(f"Definition not found: {kind}/{identifier}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = _validate(kind, identifier, yaml.safe_load(raw))
    except yaml.YAMLError as exc:
        raise RegistryError(f"Invalid YAML: {exc}") from exc
    return {"kind": kind, "id": identifier, "data": data, "raw": raw}


def save_definition(
    kind: str, identifier: str, raw: str, *, allow_agent_promotion: bool = False
) -> dict[str, Any]:
    try:
        data = _validate(kind, identifier, yaml.safe_load(raw))
    except yaml.YAMLError as exc:
        raise RegistryError(f"Invalid YAML: {exc}") from exc
    if kind == "agents" and data.get("status") == "promoted" and not allow_agent_promotion:
        data["status"] = "draft"
        data.pop("promotion", None)
    normalized = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    _path(kind, identifier).write_text(normalized, encoding="utf-8")
    return get_definition(kind, identifier)


def delete_definition(kind: str, identifier: str) -> None:
    path = _path(kind, identifier)
    if not path.exists():
        raise RegistryError(f"Definition not found: {kind}/{identifier}")
    path.unlink()
