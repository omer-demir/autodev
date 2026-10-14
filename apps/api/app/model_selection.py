from dataclasses import dataclass
from typing import Any

from .model_catalog import list_provider_models


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model: str
    source: str
    agent_provider: str | None = None
    agent_model: str | None = None
    agent_preference_available: bool | None = None


async def resolve_agent_model(
    agent_definition: dict[str, Any],
    *,
    task_model: str | None,
    configured_provider: str,
    configured_model: str,
) -> ModelSelection:
    """Prefer a concrete agent model when available, then use the task fallback."""
    model_config = agent_definition.get("model")
    if not isinstance(model_config, dict):
        model_config = {}
    agent_provider = str(model_config.get("provider") or "").casefold() or None
    agent_model = str(model_config.get("name") or "").strip() or None

    if agent_provider and agent_model and agent_model != "auto":
        available = False
        try:
            models = await list_provider_models(agent_provider)
            available_names = {
                str(value)
                for item in models
                for value in (item.get("id"), item.get("name"))
                if value
            }
            available = agent_model in available_names
        except RuntimeError:
            available = False
        if available:
            return ModelSelection(
                provider=agent_provider,
                model=agent_model,
                source="agent_preference",
                agent_provider=agent_provider,
                agent_model=agent_model,
                agent_preference_available=True,
            )

    fallback_model = (task_model or "").strip() or configured_model
    fallback_source = "task_fallback" if (
        task_model or "").strip() else "configured_default"
    if agent_provider and agent_model == "auto" and not (task_model or "").strip():
        return ModelSelection(
            provider=agent_provider,
            model="auto",
            source="agent_preference",
            agent_provider=agent_provider,
            agent_model=agent_model,
            agent_preference_available=True,
        )
    return ModelSelection(
        provider=configured_provider.casefold(),
        model=fallback_model,
        source=fallback_source,
        agent_provider=agent_provider,
        agent_model=agent_model,
        agent_preference_available=(
            False if agent_provider and agent_model and agent_model != "auto" else None
        ),
    )
