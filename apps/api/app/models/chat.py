from datetime import datetime

from sqlalchemy import Column, JSON, LargeBinary
from sqlmodel import Field, SQLModel

from .common import now


class ChatConversation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    status: str = "DONE"
    last_error: str | None = None
    selected_agents: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    additional_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    model_name: str | None = None
    model_provider: str
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class ChatTurn(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    chat_id: str = Field(foreign_key="chatconversation.id", index=True)
    role: str
    content: str
    model_provider: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    cost_note: str | None = None
    created_at: datetime = Field(default_factory=now)


class ChatAttachment(SQLModel, table=True):
    id: str = Field(primary_key=True)
    message_id: int = Field(foreign_key="chatturn.id", index=True)
    name: str
    media_type: str
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(default_factory=now)
