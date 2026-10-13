from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class GitHubInstallation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    connector_id: str | None = Field(
        default=None, foreign_key="connector.id", index=True
    )
    organization_id: str = Field(index=True)
    owner_id: str | None = Field(default=None, index=True)
    installation_id: int = Field(index=True)
    app_id: str = Field(index=True)
    app_slug: str
    bot_id: int | None = None
    account_login: str = Field(index=True)
    account_type: str = "User"
    repository_selection: str = "selected"
    permissions: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
