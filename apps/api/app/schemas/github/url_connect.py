from pydantic import BaseModel, Field


class GitHubUrlConnect(BaseModel):
    url: str = Field(min_length=19, max_length=500)
