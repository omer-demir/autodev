from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from sqlmodel import Session
from unittest.mock import MagicMock, patch

from app.database import create_db_and_tables, engine
from app.observability import _attributes, observe_event
from app.workflow import record_event


def test_exported_attributes_exclude_sensitive_payloads() -> None:
    attributes = _attributes({
        "provider": "copilot",
        "model": "auto",
        "arguments": ["cat", "/workspace/secret"],
        "prompt": "private task prompt",
        "output": "private tool output",
        "path": "/workspace/private.py",
    })

    assert attributes == {
        "autodev.provider": "copilot",
        "autodev.model": "auto",
    }


def test_model_call_counts_attempt_before_completion() -> None:
    instruments = {"model_calls": MagicMock(), "events": MagicMock()}

    with patch("app.observability._runtime_instruments", return_value=instruments):
        observe_event("model.call", "info", {
            "provider": "copilot", "model": "gpt-test",
        })

    instruments["model_calls"].add.assert_called_once_with(1, {
        "autodev.provider": "copilot", "autodev.model": "gpt-test",
        "autodev.type": "model.call", "autodev.severity": "info",
    })


@pytest.mark.asyncio
async def test_persisted_event_carries_active_trace_correlation() -> None:
    create_db_and_tables()
    provider = TracerProvider()
    local_tracer = provider.get_tracer("test")
    task_id = f"TRACE-{uuid4()}"

    with (
        local_tracer.start_as_current_span("agent.session") as span,
        Session(engine) as session,
    ):
        event = await record_event(
            session, task_id, "test.event", "Trace test", data={"status": "ok"}
        )

    span_context = span.get_span_context()
    assert event.data["trace_id"] == trace_id(span_context.trace_id)
    assert event.data["span_id"] == span_id(span_context.span_id)
    assert event.data["status"] == "ok"


def trace_id(value: int) -> str:
    return format(value, "032x")


def span_id(value: int) -> str:
    return format(value, "016x")
