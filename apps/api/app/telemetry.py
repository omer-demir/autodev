import json
from collections import Counter, defaultdict
from datetime import datetime
from itertools import pairwise
from typing import Any

from sqlmodel import Session, col, select

from .config import get_settings
from .models import Approval, Event, Message, Task, TaskArtifact


def _milliseconds(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() * 1000))


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _usage_tokens(usage: dict[str, Any]) -> tuple[int | None, int | None]:
    input_tokens = next(
        (_integer(usage.get(key)) for key in ("input_tokens", "prompt_tokens", "inputTokens")
         if _integer(usage.get(key)) is not None),
        None,
    )
    output_tokens = next(
        (_integer(usage.get(key)) for key in ("output_tokens", "completion_tokens", "outputTokens")
         if _integer(usage.get(key)) is not None),
        None,
    )
    return input_tokens, output_tokens


def _pricing(discovered: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    try:
        configured = json.loads(get_settings().model_pricing_json)
    except (json.JSONDecodeError, TypeError):
        configured = {}
    configured = configured if isinstance(configured, dict) else {}
    return {**(discovered or {}), **configured}


def _call_cost(
    pricing: dict[str, dict[str, Any]], provider: str, model: str,
    input_tokens: int | None, output_tokens: int | None,
    cache_read_tokens: int = 0, cache_write_tokens: int = 0,
) -> tuple[float | None, str]:
    if provider == "ollama":
        return 0.0, "Local inference API charge; hardware and energy costs excluded"
    rate = pricing.get(f"{provider}/{model}") or pricing.get(f"{provider}/*")
    if not isinstance(rate, dict):
        return None, "No rate card configured"
    long_context = rate.get("long_context")
    if (
        isinstance(long_context, dict)
        and input_tokens is not None
        and input_tokens > int(long_context.get("threshold_input_tokens") or 0)
    ):
        rate = {**rate, **long_context}
    request_cost = float(rate.get("per_request_usd", 0))
    if input_tokens is None or output_tokens is None:
        return (request_cost, "Configured per-request rate") if request_cost else (
            None, "Token usage unavailable for configured rate card"
        )
    uncached_input = max(
        0, input_tokens - cache_read_tokens - cache_write_tokens)
    cost = request_cost + (
        uncached_input * float(rate.get("input_per_million_usd", 0))
        + cache_read_tokens * float(rate.get("cache_read_per_million_usd", 0))
        + cache_write_tokens *
        float(rate.get("cache_write_per_million_usd", 0))
        + output_tokens * float(rate.get("output_per_million_usd", 0))
    ) / 1_000_000
    cost *= 1 - float(rate.get("discount_percent", 0)) / 100
    return round(cost, 8), str(rate.get("source") or "Configured rate card estimate")


def _phase_timings(events: list[Event]) -> list[dict[str, Any]]:
    if len(events) < 2:
        return []
    boundaries = {
        "repository.materializing": "Repository",
        "agent.started": "Implementation",
        "agent.completed": "Testing",
        "test.completed": "Security",
        "security.completed": "Review",
        "approval.created": "Approval",
        "task.completed": "Done",
        "task.failed": "Failed",
    }
    current = "Intake"
    totals: dict[str, int] = defaultdict(int)
    for event, following in pairwise(events):
        current = boundaries.get(event.type, current)
        totals[current] += _milliseconds(event.created_at,
                                         following.created_at)
    return [
        {"phase": phase, "duration_ms": duration}
        for phase, duration in totals.items()
        if duration > 0 and phase not in {"Done", "Failed"}
    ]


def _run_telemetry(
    task: Task,
    events: list[Event],
    messages: list[Message],
    approvals: list[Approval],
    artifacts: list[TaskArtifact],
    pricing: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    started_at = events[0].created_at if events else task.created_at
    ended_at = events[-1].created_at if events else task.updated_at
    model_calls: list[dict[str, Any]] = []
    pending_model: Event | None = None
    tool_requests: list[Event] = []
    tools: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    guardrails: list[dict[str, Any]] = []
    fallback_count = 0
    model_error_count = 0

    for event in events:
        elapsed_ms = _milliseconds(started_at, event.created_at)
        timeline.append({
            "id": event.id,
            "type": event.type,
            "title": event.title,
            "detail": event.detail[:2000],
            "severity": event.severity,
            "created_at": event.created_at,
            "elapsed_ms": elapsed_ms,
            "trace_id": event.data.get("trace_id"),
            "span_id": event.data.get("span_id"),
        })
        if event.type == "model.call":
            pending_model = event
        elif event.type == "model.completed":
            usage = event.data.get("usage") if isinstance(
                event.data.get("usage"), dict) else {}
            input_tokens, output_tokens = _usage_tokens(usage)
            cache_read_tokens = _integer(usage.get("cache_read_tokens")) or 0
            cache_write_tokens = _integer(usage.get("cache_write_tokens")) or 0
            provider = str(event.data.get("provider") or "unknown")
            model = str(event.data.get("model") or task.model_name or "auto")
            cost_usd, cost_basis = _call_cost(
                pricing, provider, model, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens,
            )
            inferred_latency = (
                _milliseconds(pending_model.created_at, event.created_at)
                if pending_model else None
            )
            model_calls.append({
                "sequence": len(model_calls) + 1,
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": _integer(event.data.get("latency_ms")) or inferred_latency,
                "cost_usd": cost_usd,
                "cost_basis": cost_basis,
                "fallback": bool(event.data.get("fallback")),
                "created_at": event.created_at,
            })
            pending_model = None
        elif event.type == "model.fallback":
            fallback_count += 1
        elif event.type == "model.error":
            model_error_count += 1
        elif event.type == "tool.requested":
            tool_requests.append(event)
        elif event.type == "tool.completed":
            requested = tool_requests.pop(0) if tool_requests else None
            tools.append({
                "sequence": len(tools) + 1,
                "name": event.title,
                "capability": event.data.get("capability"),
                "latency_ms": _integer(event.data.get("latency_ms")) or (
                    _milliseconds(requested.created_at,
                                  event.created_at) if requested else None
                ),
                "status": "completed",
                "created_at": event.created_at,
            })
        if event.type in {
            "tool.allowed", "tool.denied", "approval.created", "approval.approved",
            "approval.denied", "security.completed", "model.protocol_warning",
            "model.recovery_required", "model.recovery_resolved",
        }:
            guardrails.append({
                "type": event.type,
                "title": event.title,
                "detail": event.detail[:2000],
                "severity": event.severity,
                "capability": event.data.get("capability"),
                "decision": event.data.get("decision"),
                "policy": event.data.get("policy"),
                "created_at": event.created_at,
            })

    security = next(
        (artifact.content for artifact in artifacts if artifact.kind == "security"), {}
    )
    approval_details = [{
        "id": approval.id,
        "action": approval.action,
        "status": approval.status,
        "wait_ms": _milliseconds(approval.created_at, approval.decided_at)
        if approval.decided_at else None,
        "created_at": approval.created_at,
        "decided_at": approval.decided_at,
    } for approval in approvals]
    known_costs = [call["cost_usd"]
                   for call in model_calls if call["cost_usd"] is not None]
    input_values = [call["input_tokens"]
                    for call in model_calls if call["input_tokens"] is not None]
    output_values = [call["output_tokens"]
                     for call in model_calls if call["output_tokens"] is not None]
    denied = [item for item in guardrails if item["type"]
              in {"tool.denied", "approval.denied"}]

    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "phase": task.phase,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": _milliseconds(started_at, ended_at),
        "trace_id": next(
            (event.data.get("trace_id")
             for event in events if event.data.get("trace_id")),
            None,
        ),
        "model_calls": model_calls,
        "tools": tools,
        "messages": [{
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        } for message in messages],
        "timeline": timeline,
        "phase_timings": _phase_timings(events),
        "safety": {
            "allowed_actions": sum(item["type"] == "tool.allowed" for item in guardrails),
            "denied_actions": len(denied),
            "fallbacks": fallback_count,
            "model_errors": model_error_count,
            "security": {
                "high": int(security.get("high", 0)),
                "medium": int(security.get("medium", 0)),
                "low": int(security.get("low", 0)),
                "scanners": security.get("scanners", {}),
            },
            "approvals": approval_details,
            "guardrails": guardrails,
        },
        "totals": {
            "input_tokens": sum(input_values),
            "output_tokens": sum(output_values),
            "tokenized_calls": sum(
                call["input_tokens"] is not None or call["output_tokens"] is not None
                for call in model_calls
            ),
            "model_calls": len(model_calls),
            "tool_calls": len(tools),
            "estimated_cost_usd": round(sum(known_costs), 8) if known_costs else None,
            "priced_calls": len(known_costs),
            "unpriced_calls": len(model_calls) - len(known_costs),
        },
    }


def build_agent_telemetry(
    session: Session, agent_id: str, limit: int = 20,
    discovered_pricing: dict[str, dict[str, Any]] | None = None,
    organization_id: str = "local",
) -> dict[str, Any]:
    canonical_id = agent_id.removeprefix("did:local:")
    task_agent_id = f"did:local:{canonical_id}"
    tasks = session.exec(
        select(Task).where(
            col(Task.agent_id).in_([canonical_id, task_agent_id]),
            Task.organization_id == organization_id,
        ).order_by(col(Task.created_at).desc()).limit(limit)
    ).all()
    pricing = _pricing(discovered_pricing)
    runs: list[dict[str, Any]] = []
    for task in tasks:
        events = session.exec(
            select(Event).where(Event.task_id == task.id).order_by(
                Event.created_at, Event.id)
        ).all()
        messages = session.exec(
            select(Message).where(Message.task_id ==
                                  task.id).order_by(Message.created_at)
        ).all()
        approvals = session.exec(
            select(Approval).where(Approval.task_id ==
                                   task.id).order_by(Approval.created_at)
        ).all()
        artifacts = session.exec(
            select(TaskArtifact).where(TaskArtifact.task_id == task.id)
        ).all()
        runs.append(_run_telemetry(task, events, messages,
                    approvals, artifacts, pricing))

    model_calls = [call for run in runs for call in run["model_calls"]]
    known_costs = [call["cost_usd"]
                   for call in model_calls if call["cost_usd"] is not None]
    providers = Counter(
        f"{call['provider']}/{call['model']}" for call in model_calls)
    durations = [run["duration_ms"] for run in runs]
    input_tokens = sum(run["totals"]["input_tokens"] for run in runs)
    output_tokens = sum(run["totals"]["output_tokens"] for run in runs)
    denied_actions = sum(run["safety"]["denied_actions"] for run in runs)
    return {
        "agent_id": canonical_id,
        "generated_at": datetime.now().astimezone(),
        "pricing": {
            "currency": "USD",
            "status": "complete" if model_calls and len(known_costs) == len(model_calls)
            else "partial" if known_costs else "unavailable",
            "note": (
                "Copilot estimates use billing metadata advertised by the authenticated CLI; "
                "WORKBENCH_MODEL_PRICING_JSON can override those rates. Ollama shows zero API "
                "charge and excludes hardware and energy."
            ),
        },
        "summary": {
            "runs": len(runs),
            "completed_runs": sum(str(run["status"]) == "DONE" for run in runs),
            "failed_runs": sum(str(run["status"]) == "FAILED" for run in runs),
            "total_duration_ms": sum(durations),
            "average_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
            "model_calls": len(model_calls),
            "tool_calls": sum(run["totals"]["tool_calls"] for run in runs),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokenized_calls": sum(run["totals"]["tokenized_calls"] for run in runs),
            "estimated_cost_usd": round(sum(known_costs), 8) if known_costs else None,
            "priced_calls": len(known_costs),
            "unpriced_calls": len(model_calls) - len(known_costs),
            "denied_actions": denied_actions,
            "fallbacks": sum(run["safety"]["fallbacks"] for run in runs),
            "model_errors": sum(run["safety"]["model_errors"] for run in runs),
            "providers": dict(providers),
        },
        "runs": runs,
    }


def build_task_telemetry(
    session: Session, task_id: str,
    discovered_pricing: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    task = session.get(Task, task_id)
    if not task:
        return None
    events = session.exec(
        select(Event).where(Event.task_id == task.id).order_by(
            Event.created_at, Event.id)
    ).all()
    messages = session.exec(
        select(Message).where(Message.task_id ==
                              task.id).order_by(Message.created_at)
    ).all()
    approvals = session.exec(
        select(Approval).where(Approval.task_id ==
                               task.id).order_by(Approval.created_at)
    ).all()
    artifacts = session.exec(
        select(TaskArtifact).where(TaskArtifact.task_id == task.id)
    ).all()
    return _run_telemetry(
        task, events, messages, approvals, artifacts, _pricing(
            discovered_pricing)
    )
