from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from ..common import now


class EvaluationRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    agent_version: str
    suite_id: str
    suite_version: str
    status: str = "COMPLETED"
    evaluator: str = "declaration-v1"
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    overall_score: float
    scores: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    results: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON))
    dataset_id: str | None = Field(default=None, index=True)
    metrics: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    comparison: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    provenance: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
