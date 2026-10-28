from datetime import datetime

from sqlalchemy import Column, JSON
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
    selected_agents: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    additional_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    is_chat: bool = False
    approval_strategy: str = "agent_policy"
    mode: str = "change"
    verbose_logging: bool = False
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
