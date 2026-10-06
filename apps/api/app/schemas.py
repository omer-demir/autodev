from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    repository_path: str = Field(min_length=1)
    source_type: str = Field(default="local", pattern="^(local|github)$")
    repository_url: str | None = None
    default_branch: str | None = None


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=5000)
    model_name: str | None = None
    mode: str = Field(default="change", pattern="^(change|assessment)$")
    verbose_logging: bool = False
    agent_id: str = Field(default="did:local:developer",
                          pattern=r"^did:local:[a-z0-9][a-z0-9._-]{0,99}$")


class TaskModeUpdate(BaseModel):
    mode: str = Field(pattern="^(change|assessment)$")


class ModelRecoveryResolve(BaseModel):
    action: Literal["retry", "change_model", "fallback", "cancel"]
    model: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_changed_model(self):
        if self.action == "change_model" and not self.model:
            raise ValueError("model is required when changing model")
        return self


class TerminalCommand(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class GitHubConnect(BaseModel):
    owner: str = Field(min_length=1, max_length=100,
                       pattern=r"^[A-Za-z0-9_.-]+$")


class GitHubUrlConnect(BaseModel):
    url: str = Field(min_length=19, max_length=500)


class TaskMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class SessionContinuation(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    agent_id: str | None = Field(
        default=None,
        pattern=r"^did:local:[a-z0-9][a-z0-9._-]{0,99}$",
    )


class PublishRequest(BaseModel):
    branch: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9._/-]+$",
    )
    create_pull_request: bool = False

    @field_validator("branch")
    @classmethod
    def validate_git_branch(cls, value: str) -> str:
        if (
            value[0] in "./"
            or value[-1] in "./"
            or ".." in value
            or "//" in value
            or "@{" in value
        ):
            raise ValueError("branch is not a valid Git reference name")
        return value


class RegistryDefinitionUpdate(BaseModel):
    raw: str = Field(min_length=3, max_length=100_000)


class IntegrationImportRequest(BaseModel):
    url: str = Field(min_length=12, max_length=1000)
    kind: Literal["auto", "agent", "skill"] = "auto"
    identifier: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$"
    )


class EvaluationRunCreate(BaseModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    suite_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")


class EvaluationDatasetCreate(EvaluationRunCreate):
    generation_model: str | None = None


class EvaluationDatasetUpdate(BaseModel):
    scenarios: list[dict] = Field(min_length=1, max_length=100)
    reviewed_by: str = Field(min_length=1, max_length=100)


class EvaluationDatasetFreeze(BaseModel):
    reviewed_by: str = Field(min_length=1, max_length=100)


class BehavioralEvaluationRunCreate(BaseModel):
    dataset_id: str = Field(pattern=r"^DATASET-[A-Z0-9]{12}$")
    model_name: str | None = None
    adapters: list[str] = Field(default_factory=lambda: [
                                "native", "vally", "waza"])


class SecurityEvaluationRunCreate(BaseModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    include_foundry: bool = True
