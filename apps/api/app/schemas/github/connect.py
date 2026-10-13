from pydantic import BaseModel, Field


class GitHubConnect(BaseModel):
    owner: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
