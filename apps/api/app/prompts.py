import json
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined


ROOT = Path(__file__).resolve().parents[3]
PROMPTS = ROOT / "prompts"
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ENVIRONMENT = Environment(
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)
_MAX_COMPOSED_INSTRUCTIONS = 120_000


class PromptError(ValueError):
    pass


def _load(name: str) -> tuple[dict[str, Any], str]:
    if not _NAME.fullmatch(name):
        raise PromptError(f"Invalid prompt name: {name}")
    path = (PROMPTS / f"{name}.prompty").resolve()
    if PROMPTS.resolve() not in path.parents or not path.is_file():
        raise PromptError(f"Prompt not found: {name}")
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise PromptError(f"Prompt {name} is missing Prompty frontmatter")
    try:
        frontmatter, body = raw[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise PromptError(
            f"Prompt {name} has invalid Prompty frontmatter") from exc
    metadata = yaml.safe_load(frontmatter) or {}
    if not isinstance(metadata, dict):
        raise PromptError(f"Prompt {name} frontmatter must be a mapping")
    return metadata, body


def render_prompt(name: str, **values: Any) -> str:
    metadata, body = _load(name)
    inputs = metadata.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise PromptError(f"Prompt {name} inputs must be a mapping")
    missing = [
        key for key, definition in inputs.items()
        if key not in values
        and (not isinstance(definition, dict) or "default" not in definition)
    ]
    if missing:
        raise PromptError(
            f"Prompt {name} is missing inputs: {', '.join(sorted(missing))}")
    context = {
        key: values.get(key, definition.get("default")
                        if isinstance(definition, dict) else None)
        for key, definition in inputs.items()
    }
    unexpected = sorted(set(values) - set(inputs))
    if unexpected:
        raise PromptError(
            f"Prompt {name} received unknown inputs: {', '.join(unexpected)}")
    return _ENVIRONMENT.from_string(body).render(**context).strip()


def compose_agent_instructions(definition: dict[str, Any]) -> str:
    from .registry import get_definition

    sections: list[str] = []
    local = definition.get("instructions")
    if isinstance(local, str) and local.strip():
        sections.append(f"## Agent instructions\n{local.strip()}")
    for skill_id in definition.get("skills", []):
        skill = get_definition("skills", str(skill_id))["data"]
        sections.append(
            f"## Skill: {skill['name']}\n"
            f"{str(skill['instructions']).strip()}"
        )
    composed = "\n\n".join(sections)
    if len(composed) > _MAX_COMPOSED_INSTRUCTIONS:
        raise PromptError(
            f"Agent and skill instructions exceed {_MAX_COMPOSED_INSTRUCTIONS} characters"
        )
    return composed


def render_agent_system_prompt(
    definition: dict[str, Any],
    *,
    agent_id: str,
    task_mode: str,
    max_tool_calls: int,
    max_shell_calls: int,
) -> str:
    capabilities = sorted(str(item)
                          for item in definition.get("capabilities", []))
    denied = sorted(str(item) for item in definition.get("deny", []))
    environment = definition.get("environment", {})
    return render_prompt(
        "coding-agent-system",
        agent_name=str(definition.get("name", agent_id)),
        agent_version=str(definition.get("version", "unknown")),
        capabilities_json=json.dumps(capabilities),
        denied_json=json.dumps(denied),
        task_mode=task_mode,
        setup_instructions=str(environment.get("setup_instructions", "")),
        extension_instructions=compose_agent_instructions(definition),
        max_tool_calls=max_tool_calls,
        max_shell_calls=max_shell_calls,
    )
