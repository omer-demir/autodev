from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class ConnectorCredential(SQLModel, table=True):
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    owner_id: str | None = Field(default=None, index=True)
    provider: str = Field(index=True)
    login: str | None = None
    encrypted_secret: str | None = None
    secret_reference: str | None = None
    method: str = "oauth"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
