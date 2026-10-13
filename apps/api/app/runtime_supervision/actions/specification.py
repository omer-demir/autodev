from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    capability: str
    read_only: bool = False
    reversible: bool = True
    undo_api: str | None = None
    is_admin: bool = False
    command: str | None = None
