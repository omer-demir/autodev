from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from ..common import now


class ExecutionJob(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    operation: str = Field(default="run", index=True)
    status: str = Field(default="QUEUED", index=True)
    deduplication_key: str | None = Field(default=None, unique=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    worker_id: str | None = Field(default=None, index=True)
    lease_token: str | None = None
    leased_until: datetime | None = Field(default=None, index=True)
    attempts: int = 0
    max_attempts: int = 3
    cancel_requested: bool = False
    error: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
