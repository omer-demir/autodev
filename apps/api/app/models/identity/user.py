from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)
    email: str | None = None
    display_name: str | None = None
    issuer: str = "local"
    created_at: datetime = Field(default_factory=now)
