from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    INTAKE = "INTAKE"
    PLANNING = "PLANNING"
    IMPLEMENTATION = "IMPLEMENTATION"
    AWAITING_MODEL = "AWAITING_MODEL"
    TESTING = "TESTING"
    SECURITY = "SECURITY"
    REVIEW = "REVIEW"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)
    email: str | None = None
    display_name: str | None = None
    issuer: str = "local"
    created_at: datetime = Field(default_factory=now)


class Organization(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=now)


class Membership(SQLModel, table=True):
    user_id: str = Field(foreign_key="user.id", primary_key=True)
    organization_id: str = Field(
        foreign_key="organization.id", primary_key=True)
    role: str = "viewer"
    created_at: datetime = Field(default_factory=now)


class AgentIdentityRecord(SQLModel, table=True):
    did: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    public_key: str
    verification_key_id: str
    sponsor_id: str
    sponsor_email: str
    sponsor_verified: bool = False
    status: str = "active"
    capabilities: list[str] = Field(
        default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class MarketplaceEntry(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    agent_did: str = Field(index=True)
    manifest: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    verified: bool = False
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    repository_path: str
    source_type: str = "local"
    repository_url: str | None = None
    default_branch: str | None = None
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=now)


class Task(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    title: str
    description: str
    status: TaskStatus = Field(default=TaskStatus.DRAFT)
    phase: str = "Intake"
    progress: int = 0
    agent_id: str = "did:local:developer"
    branch: str = "feature/agent-task"
    model_name: str | None = None
    mode: str = "change"
    verbose_logging: bool = False
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    type: str
    title: str
    detail: str = ""
    severity: str = "info"
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Approval(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    action: str
    organization_id: str = Field(default="local", index=True)
    scope: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "PENDING"
    reason: str = "Policy requires human approval"
    requester_id: str | None = None
    approver_id: str | None = None
    created_at: datetime = Field(default_factory=now)
    decided_at: datetime | None = None


class Sandbox(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    provider: str = "docker"
    status: str = "READY"
    workspace: str = "/workspace/project"
    network_policy: str = "restricted"
    container_id: str | None = None
    host_workspace: str | None = None
    created_at: datetime = Field(default_factory=now)


class TaskArtifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    kind: str
    content: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    role: str
    content: str
    created_at: datetime = Field(default_factory=now)


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


class EvaluationDataset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    agent_version: str
    suite_id: str
    suite_version: str
    status: str = Field(default="DRAFT", index=True)
    scenarios: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON))
    content_hash: str | None = None
    generated_by: str = "deterministic-v1"
    organization_id: str = Field(default="local", index=True)
    created_by: str | None = None
    reviewed_by: str | None = None
    frozen_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
