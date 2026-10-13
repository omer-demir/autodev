from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class WorkspaceRevision(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    organization_id: str = Field(index=True)
    parent_id: str | None = Field(default=None, index=True)
    digest: str = Field(index=True)
    object_key: str
    size_bytes: int
    created_at: datetime = Field(default_factory=now)
