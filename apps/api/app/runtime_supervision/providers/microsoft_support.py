import json
from hashlib import sha256
from typing import Any

from ..actions import ActionSpec
from ..sessions import SessionHandle


def action_descriptor(action: ActionSpec) -> Any:
    from hypervisor.models import ActionDescriptor, ReversibilityLevel

    reversibility = (
        ReversibilityLevel.FULL
        if action.reversible
        else ReversibilityLevel.NONE
    )
    return ActionDescriptor(
        action_id=action.capability.replace("/", "."),
        name=action.capability,
        execute_api=f"workbench://{action.capability}",
        undo_api=action.undo_api,
        reversibility=reversibility,
        undo_window_seconds=300 if action.undo_api else 0,
        is_read_only=action.read_only,
        is_admin=action.is_admin,
    )


def kill_reason(reason: str, kill_reason_type: Any) -> Any:
    normalized = reason.lower()
    if "rate" in normalized:
        return kill_reason_type.RATE_LIMIT
    if "breach" in normalized:
        return kill_reason_type.RING_BREACH
    if "timeout" in normalized:
        return kill_reason_type.SESSION_TIMEOUT
    if "drift" in normalized:
        return kill_reason_type.BEHAVIORAL_DRIFT
    return kill_reason_type.MANUAL


def terminal_commitment(handle: SessionHandle, reason: str, kill: Any) -> str:
    payload = {
        "agent_id": handle.agent_id,
        "kill_id": kill.kill_id,
        "provider": handle.provider,
        "reason": reason,
        "session_id": handle.session_id,
        "task_id": handle.metadata.get("task_id"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()
