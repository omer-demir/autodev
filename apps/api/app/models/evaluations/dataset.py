from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class EvaluationDataset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    dataset_name: str = Field(default="", index=True)
    version: int = 1
    agent_id: str = Field(index=True)
    agent_version: str
    suite_id: str
    suite_version: str
    status: str = Field(default="DRAFT", index=True)
    scenarios: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON))
    adapter_specs: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    content_hash: str | None = None
    generated_by: str = "deterministic-v1"
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    reviewed_by: str | None = None
    frozen_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
