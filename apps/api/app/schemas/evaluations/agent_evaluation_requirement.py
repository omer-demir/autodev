from pydantic import BaseModel, Field


class AgentEvaluationRequirement(BaseModel):
    evaluation_required: bool
    reason: str = Field(min_length=3, max_length=500)
