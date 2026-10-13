from datetime import datetime

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class AgentIdentityRecord(SQLModel, table=True):
    did: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    public_key: str
    verification_key_id: str
    sponsor_id: str
    sponsor_email: str
    sponsor_verified: bool = False
    status: str = "active"
    capabilities: list[str] = Field(
        default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
