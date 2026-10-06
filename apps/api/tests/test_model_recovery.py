import asyncio

import pytest

from app.model_recovery import ModelRecoveryBroker, ModelRecoveryDecision


@pytest.mark.asyncio
async def test_operator_can_resolve_pending_model_recovery() -> None:
    broker = ModelRecoveryBroker()
    pending = asyncio.create_task(broker.request(
        task_id="TASK-RECOVERY",
        provider="copilot",
        model="gpt-test",
        fallback_provider="ollama",
        fallback_model="gemma-test",
        error="transient timeout",
        attempts=1,
        timeout=10,
    ))
    await asyncio.sleep(0)

    request = broker.get("TASK-RECOVERY")
    assert request is not None
    assert request["error"] == "transient timeout"
    assert broker.resolve(
        "TASK-RECOVERY", ModelRecoveryDecision("change_model", "gpt-other")
    ) is True
    assert await pending == ModelRecoveryDecision("change_model", "gpt-other")
    assert broker.get("TASK-RECOVERY") is None


@pytest.mark.asyncio
async def test_model_recovery_timeout_selects_fallback() -> None:
    broker = ModelRecoveryBroker()

    decision = await broker.request(
        task_id="TASK-TIMEOUT",
        provider="copilot",
        model="gpt-test",
        fallback_provider="ollama",
        fallback_model="gemma-test",
        error="transient timeout",
        attempts=1,
        timeout=0,
    )

    assert decision == ModelRecoveryDecision("fallback")
    assert broker.get("TASK-TIMEOUT") is None
