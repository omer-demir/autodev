from typing import Any


def resolved_tools(harness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]): item for item in harness.get("tools", [])}


def foundry_tool_schemas(harness: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "type": "function",
        "name": str(item["name"]),
        "description": str(item["description"]),
        "parameters": item["input_schema"],
    } for item in harness.get("tools", [])]
