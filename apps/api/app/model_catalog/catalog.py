from typing import Any

from ..config import get_settings
from .copilot import copilot_models as _copilot_models
from .ollama import ollama_models as _ollama_models


def _foundry_models() -> list[dict[str, Any]]:
    settings = get_settings()
    configured = [
        settings.foundry_model,
        *(item.strip() for item in getattr(settings, "foundry_models", "").split(",")),
    ]
    return [
        {"name": name, "id": name, "provider": "foundry"}
        for name in dict.fromkeys(configured)
        if name
    ]


async def list_provider_models(provider: str) -> list[dict[str, Any]]:
    normalized = provider.casefold()
    if normalized == "foundry":
        settings = get_settings()
        if not settings.foundry_responses_endpoint:
            raise RuntimeError(
                "Microsoft Foundry is configured but WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
            )
        return _foundry_models()
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
        if not settings.foundry_responses_endpoint:
            raise RuntimeError(
                "Microsoft Foundry is configured but WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
            )
        return _foundry_models()
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
