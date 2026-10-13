from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class Sandbox(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    provider: str = "docker"
    status: str = "READY"
    workspace: str = "/workspace/project"
    network_policy: str = "restricted"
    container_id: str | None = None
    host_workspace: str | None = None
    workspace_revision_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now)
