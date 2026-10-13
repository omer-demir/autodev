from datetime import datetime

from sqlmodel import Field, SQLModel

from ..common import now


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    role: str
    content: str
    created_at: datetime = Field(default_factory=now)
