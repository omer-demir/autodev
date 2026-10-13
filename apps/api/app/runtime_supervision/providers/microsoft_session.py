from dataclasses import dataclass, field

from ..sessions import SessionHandle


@dataclass
class MicrosoftSession:
    handle: SessionHandle
    saga_id: str
    step_ids: dict[str, str]
    completed_steps: set[str] = field(default_factory=set)
