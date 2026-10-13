from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    repository_path: str = ""
    source_type: str = Field(default="local", pattern="^(local|github|empty)$")
    repository_url: str | None = None
    default_branch: str | None = None
    connector_id: str | None = None
    transport: str = Field(default="https", pattern="^(ssh|https)$")
