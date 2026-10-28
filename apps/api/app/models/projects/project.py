from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    repository_path: str
    source_type: str = "local"
    workspace_only: bool = False
    repository_url: str | None = None
    default_branch: str | None = None
    connector_id: str | None = Field(
        default=None, foreign_key="connector.id", index=True
    )
    transport: str = "https"
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=now)
