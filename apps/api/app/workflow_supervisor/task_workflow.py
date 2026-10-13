from dataclasses import dataclass
from typing import Any

from ..models import TaskStatus
from ..runtime_supervision import SessionHandle


@dataclass
class TaskWorkflow:
    handle: SessionHandle
    phases: dict[TaskStatus, dict[str, Any]]
