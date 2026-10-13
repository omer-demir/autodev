from pydantic import BaseModel, Field


class TaskModeUpdate(BaseModel):
    mode: str = Field(pattern="^(change|assessment)$")
