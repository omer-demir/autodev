from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class EvaluationEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    organization_id: str = Field(default="local", index=True)
    adapter: str | None = Field(default=None, index=True)
    scenario_id: str | None = Field(default=None, index=True)
    type: str = Field(index=True)
    title: str
    detail: str = ""
    severity: str = "info"
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now, index=True)
