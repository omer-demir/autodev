from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class MarketplaceEntry(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    agent_did: str = Field(index=True)
    manifest: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    verified: bool = False
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
