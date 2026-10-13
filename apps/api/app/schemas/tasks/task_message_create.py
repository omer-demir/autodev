from pydantic import BaseModel, Field


class TaskMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
