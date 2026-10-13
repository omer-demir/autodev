from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class Connector(SQLModel, table=True):
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    created_by: str | None = Field(default=None, index=True)
    provider: str = Field(index=True)
    name: str
    auth_method: str
    status: str = Field(default="DRAFT", index=True)
    account_login: str | None = Field(default=None, index=True)
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON),
    )
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)