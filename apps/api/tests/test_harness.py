from unittest.mock import patch

import pytest

from app.harness import foundry_tool_schemas, resolve_agent_harness, resolved_tools
from app.registry import RegistryError


def test_agent_harness_resolves_tool_schema_and_capability_catalog():
    harness = resolve_agent_harness("developer")
    tools = resolved_tools(harness)
    schemas = foundry_tool_schemas(harness)

    assert harness["version"] == "1.0.0"
    assert harness["resolved_capability_catalog"]["version"] == "1.0.0"
    assert tools["read_file"]["capability"] == "repository.read"
    assert next(item for item in schemas if item["name"] == "read_file") == {
        "type": "function",
        "name": "read_file",
        "description": "Read a bounded UTF-8 file chunk.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["path"],
        },
    }


def test_agent_harness_fails_closed_when_pinned_version_is_unavailable():
    documents = {
        "agents": {
            "data": {
                "harness": {"id": "workspace", "version": "9.9.9"},
            },
        },
        "harnesses": {
            "data": {
                "name": "Workspace",
                "version": "1.0.0",
                "capability_catalog": {"id": "governance", "version": "1.0.0"},
                "tools": [],
            },
        },
    }

    with patch(
        "app.harness.get_definition",
        side_effect=lambda kind, _identifier: documents[kind],
    ), pytest.raises(RegistryError, match="version 9.9.9 is unavailable"):
        resolve_agent_harness("developer")
