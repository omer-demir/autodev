from pydantic import BaseModel, Field


class EvaluationRunCreate(BaseModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    dataset_id: str = Field(pattern=r"^DATASET-[A-Z0-9]{12}$")
