from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=5000)
    model_name: str | None = None
    mode: str = Field(default="change", pattern="^(change|assessment)$")
    verbose_logging: bool = False
    workflow_id: str = Field(
        default="sdlc",
        pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$",
    )
    agent_id: str = Field(
        default="did:local:developer",
        pattern=r"^did:local:[a-z0-9][a-z0-9._-]{0,99}$",
    )
