import re
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

from ..registry import IDENTIFIER, RegistryError

ImportKind = Literal["auto", "agent", "skill"]
_SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:64] or "imported-agent"


def _markdown(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        raise RegistryError(
            "Imported Markdown must start with YAML frontmatter")
    try:
        frontmatter, body = raw[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(frontmatter) or {}
    except (ValueError, yaml.YAMLError) as exc:
        raise RegistryError(
            "Imported Markdown has invalid YAML frontmatter") from exc
    if not isinstance(metadata, dict) or not body.strip():
        raise RegistryError(
            "Imported Markdown requires metadata and instructions")
    return metadata, body.strip()


def _version(metadata: dict[str, Any]) -> str:
    nested = metadata.get("metadata")
    candidate = nested.get("version") if isinstance(nested, dict) else None
    return str(candidate or metadata.get("version") or "0.1.0")


def normalize_external_definition(
    source_url: str,
    raw: str,
    *,
    kind: ImportKind = "auto",
    identifier: str | None = None,
) -> tuple[str, str, str]:
    metadata, instructions = _markdown(raw)
    inferred = "skill" if PurePosixPath(
        urlparse(source_url).path).name == "SKILL.md" else "agent"
    selected = inferred if kind == "auto" else kind
    if selected == "skill":
        name = str(metadata.get("name") or "")
        if not _SKILL_NAME.fullmatch(name):
            raise RegistryError(
                "Skill name must use lowercase letters, numbers, and hyphens")
        skill_id = identifier or name
        if not _SKILL_NAME.fullmatch(skill_id):
            raise RegistryError(
                "Local skill ID must use lowercase letters, numbers, and hyphens")
        data = {
            "name": name,
            "version": _version(metadata),
            "description": str(metadata.get("description") or "Imported Agent Skill"),
            "instructions": instructions,
            "source": {
                "url": source_url,
                "format": "agent-skills",
                "license": metadata.get("license"),
                "compatibility": metadata.get("compatibility"),
                "declared_allowed_tools": metadata.get("allowed-tools"),
                "trust": "unreviewed",
            },
        }
        return "skills", skill_id, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    display_name = str(metadata.get("name") or "Imported Agent")
    agent_id = identifier or _slug(display_name)
    if not IDENTIFIER.fullmatch(agent_id):
        raise RegistryError("Imported agent ID is invalid")
    handoffs = metadata.get("handoffs") if isinstance(
        metadata.get("handoffs"), list) else []
    declared_skills = sorted({
        str(item.get("prompt", "")).removeprefix("/")
        for item in handoffs
        if isinstance(item, dict) and str(item.get("prompt", "")).startswith("/")
    })
    data = {
        "name": display_name,
        "version": _version(metadata),
        "description": str(metadata.get("description") or "Imported agent"),
        "status": "draft",
        "evaluation_required": True,
        "identity": {"id": f"did:local:{agent_id}"},
        "policy": "development",
        "harness": {"id": "workspace", "version": "1.0.0"},
        "environment": {
            "image": "agentic-sdlc-sandbox:local",
            "network_mode": "none",
            "workspace_access": "read-only",
            "setup_instructions": "Inspect the repository using governed read tools.",
        },
        "model": {"provider": "copilot", "name": "auto"},
        "capabilities": ["repository.read", "git.status", "git.diff"],
        "mcp_servers": ["workspace"],
        "skills": [],
        "instructions": instructions,
        "approval": ["git.commit", "git.push"],
        "deny": [
            "repository.write",
            "dependency.install",
            "production.deploy",
            "host.credentials.read",
        ],
        "source": {
            "url": source_url,
            "format": "github-copilot-agent",
            "declared_tools": metadata.get("tools"),
            "declared_skills": declared_skills,
            "trust": "unreviewed",
        },
    }
    return "agents", agent_id, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
