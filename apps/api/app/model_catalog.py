"""Runtime model discovery, separate from Agent Framework execution."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import httpx
from agent_framework.github import GitHubCopilotAgent
from agent_framework.ollama import OllamaChatClient
from copilot import CopilotClient, RuntimeConnection

from .config import get_settings

_MODEL_CACHE_SECONDS = 60.0
_copilot_model_cache: tuple[float, list[dict[str, Any]]] | None = None


def _model_dict(model: Any) -> dict[str, Any]:
    if isinstance(model, dict):
        value = dict(model)
    elif hasattr(model, "model_dump"):
        value = model.model_dump(mode="json")
    elif is_dataclass(model) and not isinstance(model, type):
        value = asdict(model)
    else:
        value = {"id": getattr(model, "id", str(model))}
    return {**value, "name": value.get("id") or value.get("name"), "provider": "copilot"}


async def _copilot_models() -> list[dict[str, Any]]:
    global _copilot_model_cache
    if _copilot_model_cache and time.monotonic() - _copilot_model_cache[0] < _MODEL_CACHE_SECONDS:
        return [dict(item) for item in _copilot_model_cache[1]]
    settings = get_settings()
    token = os.getenv("COPILOT_GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    cli_path = shutil.which(settings.copilot_cli_path)
    if not cli_path:
        raise RuntimeError(
            f"GitHub Copilot CLI '{settings.copilot_cli_path}' is not available to the API."
        )
    options: dict[str, Any] = {
        "connection": RuntimeConnection.for_stdio(path=cli_path),
        "base_directory": str(Path(settings.copilot_home).expanduser().resolve()),
    }
    if token:
        options["github_token"] = token
        options["use_logged_in_user"] = False
    try:
        async with asyncio.timeout(settings.runtime_discovery_timeout_seconds):
            async with CopilotClient(**options) as client:
                auth = await client.get_auth_status()
                if not auth.isAuthenticated:
                    raise RuntimeError(
                        "GitHub Copilot is not authenticated. Run `copilot login` using "
                        f"COPILOT_HOME={options['base_directory']} or set COPILOT_GITHUB_TOKEN."
                    )
                models = [_model_dict(item) for item in await client.list_models()]
                _copilot_model_cache = (time.monotonic(), models)
                return [dict(item) for item in models]
    except TimeoutError as exc:
        raise RuntimeError(
            "GitHub Copilot model discovery timed out after "
            f"{settings.runtime_discovery_timeout_seconds} seconds."
        ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "GitHub Copilot is unavailable. Sign in with Copilot CLI in COPILOT_HOME "
            "or set COPILOT_GITHUB_TOKEN to a token with Copilot access."
        ) from exc


async def _ollama_models(*, fallback: bool = False) -> list[dict[str, Any]]:
    url = get_settings().ollama_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        return []
    return [
        {**item, "provider": "ollama", "fallback": fallback}
        for item in response.json().get("models", [])
    ]


async def list_runtime_models() -> list[dict[str, Any]]:
    settings = get_settings()
    provider = settings.model_provider.casefold()
    if provider == "foundry":
        if not settings.foundry_responses_endpoint:
            raise RuntimeError(
                "Microsoft Foundry is configured but "
                "WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
            )
        return [{
            "name": settings.foundry_model,
            "id": settings.foundry_model,
            "provider": "foundry",
        }]
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


def _usd_rate_card(model: dict[str, Any]) -> dict[str, Any] | None:
    billing = model.get("billing")
    prices = billing.get("token_prices") if isinstance(billing, dict) else None
    if not isinstance(prices, dict) or not prices.get("batch_size"):
        return None
    batch_size = float(prices["batch_size"])
    usd_per_credit = 0.01
    per_million = 1_000_000 / batch_size

    def tier(source: dict[str, Any]) -> dict[str, float]:
        return {
            key: float(source.get(field) or 0) * usd_per_credit * per_million
            for key, field in {
                "input_per_million_usd": "input_price",
                "output_per_million_usd": "output_price",
                "cache_read_per_million_usd": "cache_read_price",
                "cache_write_per_million_usd": "cache_write_price",
            }.items()
        }

    rate: dict[str, Any] = {
        **tier(prices),
        "source": "GitHub Copilot CLI AI Credits (1 credit = $0.01 USD)",
    }
    discount = float(billing.get("discount_percent") or 0)
    if discount:
        rate["discount_percent"] = discount
    long_context = prices.get("long_context")
    if isinstance(long_context, dict):
        rate["long_context"] = {
            **tier(long_context),
            "threshold_input_tokens": int(
                prices.get("max_prompt_tokens") or prices.get(
                    "context_max") or 0
            ),
        }
    return rate


async def runtime_model_pricing() -> dict[str, dict[str, Any]]:
    """Return provider/model USD rate cards advertised by the active runtime."""
    settings = get_settings()
    if settings.model_provider.casefold() != "copilot":
        return {}
    try:
        models = await _copilot_models()
    except RuntimeError:
        return {}
    return {
        f"copilot/{model['name']}": rate
        for model in models
        if model.get("name") and (rate := _usd_rate_card(model)) is not None
    }


async def generate_text(model: str, instructions: str, prompt: str) -> str:
    """Run a non-tool Agent Framework agent for semantic evaluation."""
    settings = get_settings()
    provider = settings.model_provider.casefold()
    if provider == "ollama":
        agent = OllamaChatClient(host=settings.ollama_url, model=model).as_agent(
            instructions=instructions, default_options={"model": model}
        )
    elif provider == "copilot":
        options: dict[str, Any] = {
            "cli_path": settings.copilot_cli_path,
            "timeout": float(settings.model_request_timeout_seconds),
            "base_directory": str(Path(settings.copilot_home).expanduser().resolve()),
            "enable_file_hooks": False,
            "available_tools": [],
        }
        if model not in {"", "auto"}:
            options["model"] = model
        agent = GitHubCopilotAgent(
            instructions=instructions, default_options=options)
    else:
        raise RuntimeError(f"Unsupported model provider: {provider}")
    async with agent:
        response = await agent.run(prompt)
    return response.text
