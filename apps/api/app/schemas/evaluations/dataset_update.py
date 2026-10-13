from pydantic import BaseModel, Field


class EvaluationDatasetUpdate(BaseModel):
    scenarios: list[dict] = Field(min_length=1, max_length=100)
    reviewed_by: str = Field(min_length=1, max_length=100)
