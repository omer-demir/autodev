from typing import Any

from pydantic import BaseModel, Field


class EvaluationDatasetVersionCreate(BaseModel):
    scenarios: list[dict[str, Any]] = Field(min_length=1, max_length=100)
