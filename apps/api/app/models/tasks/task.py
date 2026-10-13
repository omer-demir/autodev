from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now
from .status import TaskStatus


class Task(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    title: str
    description: str
    status: TaskStatus = Field(default=TaskStatus.DRAFT)
    phase: str = "Intake"
    progress: int = 0
    workflow_id: str = "sdlc"
    agent_id: str = "did:local:developer"
    branch: str = "feature/agent-task"
    model_name: str | None = None
    mode: str = "change"
    verbose_logging: bool = False
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
