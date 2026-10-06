"""Agent SRE bridge for Workbench governance and task events."""

from __future__ import annotations

from typing import Any

from agent_sre import ErrorBudget, SLO
from agent_sre.incidents.detector import IncidentDetector
from agent_sre.integrations.agent_os.bridge import AgentOSBridge, AuditLogEntry
from agent_sre.slo.indicators import TaskSuccessRate
from agent_sre.slo.objectives import ExhaustionAction

from .config import get_settings


class ReliabilityBridge:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.agent_sre_enabled
        self.agent_os = AgentOSBridge()
        self.task_success = TaskSuccessRate(
            target=settings.agent_sre_task_success_target,
            window="24h",
        )
        self.slo = SLO(
            name="autodev-runtime",
            indicators=[self.agent_os.policy_sli, self.task_success],
            error_budget=ErrorBudget(
                total=settings.agent_sre_error_budget,
                exhaustion_action=ExhaustionAction.CIRCUIT_BREAK,
            ),
            description="Governance compliance and task completion reliability",
        )
        self.incidents = IncidentDetector()
        self.incidents.register_response(
            "policy_violation", ["freeze_execution", "notify_operator"]
        )

    def observe_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        values = data or {}
        if event_type in {"tool.allowed", "tool.denied"}:
            compliant = str(values.get("decision")) == "ALLOW"
            signal = self.agent_os.process_audit_entry(AuditLogEntry(
                entry_type="allowed" if compliant else "blocked",
                agent_id=str(values.get("agent_id")
                             or values.get("task_id") or "unknown"),
                action=str(values.get("capability") or "unknown"),
                policy_name=str(values.get("policy") or "unknown"),
                outcome=str(values.get("decision") or "unknown"),
                details={
                    key: values[key]
                    for key in ("task_id", "capability", "decision", "policy")
                    if key in values
                },
            ))
            self.slo.record_event(good=compliant)
            if signal is not None:
                self.incidents.ingest_signal(signal)
        elif event_type in {"task.completed", "task.failed"}:
            success = event_type == "task.completed"
            self.task_success.record_task(success, {
                "task_id": str(values.get("task_id") or "unknown")
            })
            self.slo.record_event(good=success)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "slo": self.slo.to_dict(),
            "agent_os": self.agent_os.summary(),
            "incidents": self.incidents.summary(),
            "open_incidents": [item.to_dict() for item in self.incidents.open_incidents],
        }


reliability = ReliabilityBridge()
