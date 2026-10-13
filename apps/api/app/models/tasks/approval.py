from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class Approval(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    action: str
    organization_id: str = Field(default="local", index=True)
    scope: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "PENDING"
    reason: str = "Policy requires human approval"
    requester_id: str | None = None
    approver_id: str | None = None
    created_at: datetime = Field(default_factory=now)
    decided_at: datetime | None = None
