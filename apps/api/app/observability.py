"""Privacy-bounded OpenTelemetry setup and runtime instruments."""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import UTC, datetime
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from .config import get_settings

_configured = False
_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_instruments: dict[str, Counter | Histogram] | None = None
_logging_configured = False


class _TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = trace.get_current_span().get_span_context()
        record.trace_id = format(
            context.trace_id, "032x") if context.is_valid else ""
        record.span_id = format(
            context.span_id, "016x") if context.is_valid else ""
        return True


class _PrivacySafeJsonFormatter(logging.Formatter):
    """Emit bounded operational fields without exception text or local variables."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage()[:2_000],
            "service_name": get_settings().otel_service_name,
        }
        trace_id = getattr(record, "trace_id", "")
        span_id = getattr(record, "span_id", "")
        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id
        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging() -> None:
    """Decorate process logs for Loki correlation without exporting payload data."""
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True
    context_filter = _TraceContextFilter()
    formatter = _PrivacySafeJsonFormatter()
    loggers = [logging.getLogger(), logging.getLogger("uvicorn.error")]
    for logger in loggers:
        for handler in logger.handlers:
            handler.addFilter(context_filter)
            handler.setFormatter(formatter)


def _redis_request_hook(span: Span, _instance: Any, args: tuple[Any, ...], _kwargs: Any) -> None:
    """Replace Redis statements because stream payloads may contain private task data."""
    if not span.is_recording():
        return
    command = str(args[0]).upper()[:40] if args else "REDIS"
    span.set_attribute("db.statement", command)
    span.set_attribute("db.query.text", command)


def _endpoint() -> str | None:
    configured = (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or get_settings().otel_exporter_otlp_endpoint
    )
    return configured.rstrip("/") if configured else None


def configure_observability() -> bool:
    """Configure OTLP export once. No endpoint means an intentionally quiet no-op."""
    global _configured, _meter_provider, _tracer_provider
    if _configured:
        return _tracer_provider is not None
    _configured = True
    endpoint = _endpoint()
    if not endpoint:
        return False
    resource = Resource.create({
        "service.name": get_settings().otel_service_name,
        "service.namespace": "autodev",
        "service.instance.id": os.getenv("HOSTNAME") or socket.gethostname(),
        "service.version": "0.1.0",
        "deployment.environment.name": get_settings().execution_mode,
    })
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    ))
    trace.set_tracer_provider(_tracer_provider)
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=5_000,
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)
    from .database import engine

    SQLAlchemyInstrumentor().instrument(
        engine=engine, tracer_provider=_tracer_provider)
    RedisInstrumentor().instrument(
        tracer_provider=_tracer_provider,
        request_hook=_redis_request_hook,
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=_tracer_provider)
    return True


def observability_status() -> dict[str, Any]:
    endpoint = _endpoint()
    return {
        "enabled": endpoint is not None,
        "protocol": "otlp/http" if endpoint else None,
        "endpoint": endpoint,
        "service_name": get_settings().otel_service_name,
    }


def shutdown_observability() -> None:
    if _meter_provider:
        _meter_provider.shutdown()
    if _tracer_provider:
        _tracer_provider.shutdown()


def tracer():
    return trace.get_tracer("autodev.agent", "0.1.0")


def _runtime_instruments() -> dict[str, Counter | Histogram]:
    global _instruments
    if _instruments is None:
        meter = metrics.get_meter("autodev.runtime", "0.1.0")
        _instruments = {
            "events": meter.create_counter("autodev.runtime.events", unit="{event}"),
            "sessions": meter.create_counter("autodev.agent.sessions", unit="{session}"),
            "session_duration": meter.create_histogram(
                "autodev.agent.session.duration", unit="ms"
            ),
            "model_calls": meter.create_counter("autodev.model.calls", unit="{call}"),
            "model_duration": meter.create_histogram("autodev.model.duration", unit="ms"),
            "input_tokens": meter.create_counter(
                "autodev.model.input_tokens", unit="{token}"
            ),
            "output_tokens": meter.create_counter(
                "autodev.model.output_tokens", unit="{token}"
            ),
            "tool_calls": meter.create_counter("autodev.tool.calls", unit="{call}"),
            "tool_duration": meter.create_histogram("autodev.tool.duration", unit="ms"),
            "policy_decisions": meter.create_counter(
                "autodev.governance.decisions", unit="{decision}"
            ),
            "guardrail_hits": meter.create_counter(
                "autodev.governance.guardrail_hits", unit="{hit}"
            ),
            "fallbacks": meter.create_counter("autodev.model.fallbacks", unit="{fallback}"),
            "model_errors": meter.create_counter("autodev.model.errors", unit="{error}"),
            "repository_changes": meter.create_counter(
                "autodev.repository.files_changed", unit="{file}"
            ),
            "worker_jobs": meter.create_counter(
                "autodev.worker.jobs", unit="{job}"
            ),
            "worker_job_duration": meter.create_histogram(
                "autodev.worker.job.duration", unit="ms"
            ),
            "http_requests": meter.create_counter(
                "autodev.http.server.requests", unit="{request}"
            ),
            "http_request_duration": meter.create_histogram(
                "http.server.request.duration", unit="s"
            ),
        }
    return _instruments


def _attributes(values: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Keep dimensions bounded and exclude prompts, paths, commands, and tool output."""
    allowed = {
        "agent_id", "capability", "decision", "fallback", "model", "policy",
        "operation", "provider", "status", "task_id", "tool", "type",
    }
    result: dict[str, str | int | float | bool] = {}
    for key, value in values.items():
        if key not in allowed or value is None or not isinstance(value, (str, int, float, bool)):
            continue
        result[f"autodev.{key}"] = value[:120] if isinstance(
            value, str) else value
    return result


def observe_event(event_type: str, severity: str, data: dict[str, Any] | None = None) -> None:
    values = data or {}
    attributes = _attributes({"type": event_type, **values})
    attributes["autodev.severity"] = severity
    _runtime_instruments()["events"].add(1, attributes)
    current = trace.get_current_span()
    if current.is_recording():
        current.add_event(
            event_type,
            attributes=attributes,
            timestamp=int(datetime.now(UTC).timestamp() * 1e9),
        )
    if event_type == "model.fallback":
        _runtime_instruments()["fallbacks"].add(1, attributes)
    elif event_type == "model.error":
        _runtime_instruments()["model_errors"].add(1, attributes)
    elif event_type == "model.call":
        _runtime_instruments()["model_calls"].add(1, attributes)
    elif event_type == "model.completed":
        usage = values.get("usage") if isinstance(
            values.get("usage"), dict) else {}
        input_tokens = next((usage.get(key) for key in (
            "input_tokens", "prompt_tokens", "inputTokens"
        ) if isinstance(usage.get(key), int)), None)
        output_tokens = next((usage.get(key) for key in (
            "output_tokens", "completion_tokens", "outputTokens"
        ) if isinstance(usage.get(key), int)), None)
        observe_model_completion(
            current,
            provider=str(values.get("provider") or "unknown"),
            model=str(values.get("model") or "unknown"),
            latency_ms=int(values.get("latency_ms") or 0),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            fallback=bool(values.get("fallback")),
        )
    elif event_type == "tool.completed":
        observe_tool(
            current,
            name=str(values.get("tool") or "unknown"),
            capability=str(values.get("capability") or "unknown"),
            latency_ms=int(values.get("latency_ms") or 0),
            status="completed",
        )
    elif event_type in {"tool.allowed", "tool.denied"}:
        observe_policy(
            capability=str(values.get("capability") or "unknown"),
            decision=str(values.get("decision") or "unknown"),
            policy=str(values.get("policy") or "unknown"),
        )


def observe_model_completion(
    span: Span, *, provider: str, model: str, latency_ms: int,
    input_tokens: int | None, output_tokens: int | None, fallback: bool,
) -> None:
    attributes = _attributes({
        "provider": provider, "model": model, "fallback": fallback,
    })
    span.set_attributes({
        **attributes,
        "gen_ai.operation.name": "chat",
        "gen_ai.system": provider,
        "gen_ai.request.model": model,
        **({"gen_ai.usage.input_tokens": input_tokens} if input_tokens is not None else {}),
        **({"gen_ai.usage.output_tokens": output_tokens} if output_tokens is not None else {}),
    })
    _runtime_instruments()["model_duration"].record(latency_ms, attributes)
    if input_tokens is not None:
        _runtime_instruments()["input_tokens"].add(input_tokens, attributes)
    if output_tokens is not None:
        _runtime_instruments()["output_tokens"].add(output_tokens, attributes)


def observe_tool(span: Span, *, name: str, capability: str, latency_ms: int, status: str) -> None:
    attributes = _attributes(
        {"tool": name, "capability": capability, "status": status})
    span.set_attributes({**attributes, "gen_ai.tool.name": name})
    _runtime_instruments()["tool_calls"].add(1, attributes)
    _runtime_instruments()["tool_duration"].record(latency_ms, attributes)


def observe_policy(*, capability: str, decision: str, policy: str) -> None:
    attributes = _attributes({
        "capability": capability, "decision": decision, "policy": policy,
    })
    _runtime_instruments()["policy_decisions"].add(1, attributes)
    if decision != "ALLOW":
        _runtime_instruments()["guardrail_hits"].add(1, attributes)


def observe_session(*, status: str, duration_ms: int, files_changed: int = 0) -> None:
    attributes = _attributes({"status": status})
    _runtime_instruments()["sessions"].add(1, attributes)
    _runtime_instruments()["session_duration"].record(duration_ms, attributes)
    if files_changed:
        _runtime_instruments()["repository_changes"].add(
            files_changed, attributes)


def observe_worker_job(*, operation: str, status: str, duration_ms: int) -> None:
    attributes = _attributes({"operation": operation, "status": status})
    _runtime_instruments()["worker_jobs"].add(1, attributes)
    _runtime_instruments()["worker_job_duration"].record(
        duration_ms, attributes)


def observe_http_request(
    *, method: str, route: str, status_code: int, duration_seconds: float
) -> None:
    attributes: dict[str, str | int] = {
        "http.request.method": method[:16],
        "http.route": route[:200],
        "http.response.status_code": status_code,
    }
    _runtime_instruments()["http_requests"].add(1, attributes)
    _runtime_instruments()["http_request_duration"].record(
        duration_seconds, attributes
    )


def mark_error(span: Span, exc: BaseException) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)[:500]))
