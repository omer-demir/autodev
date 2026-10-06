import re
from pathlib import Path
from typing import Any

import yaml


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
    if kind == "capability-catalogs" and not isinstance(data.get("capabilities"), list):
        raise RegistryError("Capability catalog capabilities must be a list")
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
    if kind in {"workflows", "evaluation-suites"} and not isinstance(
        data.get("phases" if kind == "workflows" else "scenarios"), list
    ):
        raise RegistryError("Phases and scenarios must be YAML lists")
    if kind == "workflows":
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
    return data


def list_definitions(kind: str) -> list[dict[str, Any]]:
    return [get_definition(kind, path.stem) for path in sorted(_directory(kind).glob("*.yaml"))]


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
