from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class TaskArtifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    kind: str
    content: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
