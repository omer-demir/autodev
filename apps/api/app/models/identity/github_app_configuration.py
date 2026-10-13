from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class GitHubAppConfiguration(SQLModel, table=True):
    connector_id: str = Field(primary_key=True, foreign_key="connector.id")
    organization_id: str = Field(index=True)
    app_id: str = Field(index=True)
    app_slug: str = Field(index=True)
    client_id: str
    encrypted_client_secret: str
    encrypted_private_key: str
    encrypted_webhook_secret: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
