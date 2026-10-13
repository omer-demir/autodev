from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class Membership(SQLModel, table=True):
    user_id: str = Field(foreign_key="user.id", primary_key=True)
    organization_id: str = Field(
        foreign_key="organization.id", primary_key=True)
    role: str = "viewer"
    created_at: datetime = Field(default_factory=now)
