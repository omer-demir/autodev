import pytest
import yaml

from app.integrations import _validate_public_https, normalize_external_definition
from app.registry import RegistryError


def test_agent_skill_import_preserves_permissions_as_advisory_metadata():
    raw = """---
name: code-review
description: Reviews code when a change needs assessment.
allowed-tools: Bash(rm:*) Read
metadata:
  version: "2.1.0"
---
# Review
Inspect the diff and report correctness risks.
"""

    kind, identifier, normalized = normalize_external_definition(
        "https://example.com/code-review/SKILL.md", raw
    )
    data = yaml.safe_load(normalized)

    assert (kind, identifier) == ("skills", "code-review")
    assert data["instructions"].startswith("# Review")
    assert data["source"]["declared_allowed_tools"] == "Bash(rm:*) Read"
    assert data["source"]["trust"] == "unreviewed"


def test_copilot_agent_import_is_draft_and_read_only_by_default():
    raw = """---
name: Internet Implementer
description: Implements changes from the internet.
tools: [execute, edit, deploy]
handoffs:
  - label: Plan
    prompt: /rpi-plan
---
# Internet Implementer
Follow the remote workflow.
"""

    kind, identifier, normalized = normalize_external_definition(
        "https://example.com/internet.agent.md", raw
    )
    data = yaml.safe_load(normalized)

    assert (kind, identifier) == ("agents", "internet-implementer")
    assert data["status"] == "draft"
    assert data["capabilities"] == [
        "repository.read", "git.status", "git.diff"]
    assert "repository.write" in data["deny"]
    assert data["source"]["declared_tools"] == ["execute", "edit", "deploy"]
    assert data["source"]["declared_skills"] == ["rpi-plan"]
    assert data["skills"] == []


def test_skill_import_rejects_invalid_agent_skills_name():
    raw = """---
name: Invalid Skill
description: Invalid uppercase name.
---
Instructions.
"""

    with pytest.raises(RegistryError, match="Skill name"):
        normalize_external_definition("https://example.com/SKILL.md", raw)


def test_skill_import_rejects_invalid_name_even_with_local_identifier():
    raw = """---
name: Invalid Skill
description: Invalid uppercase name.
---
Instructions.
"""

    with pytest.raises(RegistryError, match="Skill name"):
        normalize_external_definition(
            "https://example.com/SKILL.md", raw, identifier="valid-local-id"
        )


def test_import_url_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(RegistryError, match="public addresses"):
        _validate_public_https("https://example.com/SKILL.md")
