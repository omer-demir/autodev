from typing import Any

from .registry import RegistryError, get_definition


def _versioned_definition(kind: str, reference: Any) -> dict[str, Any]:
    if not isinstance(reference, dict) or not reference.get("id") or not reference.get("version"):
        raise RegistryError(f"{kind} reference requires id and version")
    document = get_definition(kind, str(reference["id"]))["data"]
    if str(document["version"]) != str(reference["version"]):
        raise RegistryError(
            f"{kind} {reference['id']} version {reference['version']} is unavailable"
        )
    return document


def resolve_agent_harness(agent_id: str) -> dict[str, Any]:
    agent = get_definition(
        "agents", agent_id.removeprefix("did:local:"))["data"]
    harness = _versioned_definition("harnesses", agent.get("harness"))
    catalog = _versioned_definition(
        "capability-catalogs", harness.get("capability_catalog")
    )
    return {**harness, "resolved_capability_catalog": catalog}


def resolved_tools(harness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]): item for item in harness.get("tools", [])}


def foundry_tool_schemas(harness: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "type": "function",
        "name": str(item["name"]),
        "description": str(item["description"]),
        "parameters": item["input_schema"],
    } for item in harness.get("tools", [])]
