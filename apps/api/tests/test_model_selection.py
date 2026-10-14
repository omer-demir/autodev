from unittest.mock import AsyncMock, patch

import pytest

from app.model_selection import resolve_agent_model


@pytest.mark.asyncio
async def test_available_agent_model_is_preferred_over_task_fallback():
    definition = {"model": {"provider": "copilot", "name": "agent-model"}}

    with patch(
        "app.model_selection.list_provider_models",
        new=AsyncMock(
            return_value=[{"id": "agent-model", "name": "Agent model"}]),
    ):
        selection = await resolve_agent_model(
            definition,
            task_model="task-model",
            configured_provider="copilot",
            configured_model="configured-model",
        )

    assert selection.provider == "copilot"
    assert selection.model == "agent-model"
    assert selection.source == "agent_preference"
    assert selection.agent_preference_available is True


@pytest.mark.asyncio
async def test_unavailable_agent_model_uses_task_fallback():
    definition = {"model": {"provider": "ollama", "name": "missing-model"}}

    with patch(
        "app.model_selection.list_provider_models",
        new=AsyncMock(return_value=[]),
    ):
        selection = await resolve_agent_model(
            definition,
            task_model="task-model",
            configured_provider="copilot",
            configured_model="configured-model",
        )

    assert selection.provider == "copilot"
    assert selection.model == "task-model"
    assert selection.source == "task_fallback"
    assert selection.agent_preference_available is False


@pytest.mark.asyncio
async def test_failed_availability_check_uses_configured_default():
    definition = {"model": {"provider": "ollama", "name": "offline-model"}}

    with patch(
        "app.model_selection.list_provider_models",
        new=AsyncMock(side_effect=RuntimeError("offline")),
    ):
        selection = await resolve_agent_model(
            definition,
            task_model=None,
            configured_provider="copilot",
            configured_model="configured-model",
        )

    assert selection.provider == "copilot"
    assert selection.model == "configured-model"
    assert selection.source == "configured_default"
    assert selection.agent_preference_available is False


@pytest.mark.asyncio
async def test_auto_agent_model_uses_its_declared_provider():
    selection = await resolve_agent_model(
        {"model": {"provider": "copilot", "name": "auto"}},
        task_model=None,
        configured_provider="ollama",
        configured_model="configured-model",
    )

    assert selection.provider == "copilot"
    assert selection.model == "auto"
    assert selection.source == "agent_preference"
