from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class BrowserSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    organization_id: str = Field(foreign_key="organization.id", index=True)
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=now)
