from typing import Any

from ..config import get_settings
from .copilot import copilot_models as _copilot_models
from .ollama import ollama_models as _ollama_models


def _configured_names(default: str, configured: str) -> list[str]:
    return list(dict.fromkeys(
        name.strip()
        for name in [default, *configured.split(",")]
        if name.strip()
    ))


def _foundry_responses_models(settings: Any) -> list[dict[str, Any]]:
    if not getattr(settings, "foundry_responses_endpoint", None):
        return []
    return [
        {"name": name, "id": name, "provider": "foundry"}
        for name in _configured_names(
            getattr(settings, "foundry_model", ""),
            getattr(settings, "foundry_models", ""),
        )
    ]


def _foundry_anthropic_models(settings: Any) -> list[dict[str, Any]]:
    if not getattr(settings, "foundry_anthropic_endpoint", None):
        return []
    return [
        {"name": name, "id": name, "provider": "foundry-anthropic"}
        for name in _configured_names(
            getattr(settings, "foundry_anthropic_model", ""),
            getattr(settings, "foundry_anthropic_models", ""),
        )
    ]


async def list_provider_models(provider: str) -> list[dict[str, Any]]:
    normalized = provider.casefold()
    settings = get_settings()
    if normalized == "foundry":
        models = _foundry_responses_models(settings)
        if not models:
            raise RuntimeError(
                "Microsoft Foundry Responses endpoint is not configured"
            )
        return models
    if normalized == "foundry-anthropic":
        models = _foundry_anthropic_models(settings)
        if not models:
            raise RuntimeError(
                "Microsoft Foundry Anthropic endpoint or deployment names "
                "are not configured"
            )
        return models
    if normalized == "ollama":
        return await _ollama_models()
    if normalized == "copilot":
        models = await _copilot_models()
        return [
            {"name": "auto", "id": "auto", "provider": "copilot",
             "automatic": True},
            *(item for item in models if item.get("name") != "auto"),
        ]
    raise RuntimeError(f"Unsupported model provider: {normalized}")


async def list_runtime_models() -> list[dict[str, Any]]:
    settings = get_settings()
    provider = settings.model_provider.casefold()
    if provider == "foundry":
        responses_models = _foundry_responses_models(settings)
        if not responses_models:
            raise RuntimeError(
                "Microsoft Foundry is configured but "
                "WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
            )
        return responses_models + _foundry_anthropic_models(settings)
    if provider == "foundry-anthropic":
        anthropic_models = _foundry_anthropic_models(settings)
        if not anthropic_models:
            raise RuntimeError(
                "Microsoft Foundry Anthropic is configured but "
                "WORKBENCH_FOUNDRY_ANTHROPIC_ENDPOINT or deployment names are unset"
            )
        return anthropic_models + _foundry_responses_models(settings)
    if provider == "ollama":
        return await _ollama_models()
    if provider != "copilot":
        raise RuntimeError(f"Unsupported model provider: {provider}")
    try:
        return await _copilot_models()
    except RuntimeError:
        if settings.model_fallback_provider.casefold() == "ollama":
            fallback = await _ollama_models(fallback=True)
            if fallback:
                return fallback
        raise
