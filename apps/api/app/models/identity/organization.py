from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class Organization(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=now)
