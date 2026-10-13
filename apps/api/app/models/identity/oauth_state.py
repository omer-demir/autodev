from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class OAuthState(SQLModel, table=True):
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    user_id: str = Field(index=True)
    expires_at: datetime = Field(index=True)
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
