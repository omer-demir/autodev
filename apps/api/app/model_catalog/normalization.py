from dataclasses import asdict, is_dataclass
from typing import Any


def model_dict(model: Any) -> dict[str, Any]:
    if isinstance(model, dict):
        value = dict(model)
    elif hasattr(model, "model_dump"):
        value = model.model_dump(mode="json")
    elif is_dataclass(model) and not isinstance(model, type):
        value = asdict(model)
    else:
        value = {"id": getattr(model, "id", str(model))}
    return {**value, "name": value.get("id") or value.get("name"), "provider": "copilot"}
