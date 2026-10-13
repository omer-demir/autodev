from pydantic import BaseModel, Field


class EvaluationDatasetCreate(BaseModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    generation_model: str | None = None
