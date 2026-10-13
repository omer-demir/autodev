from pydantic import BaseModel, Field


class BehavioralEvaluationRunCreate(BaseModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    dataset_id: str = Field(pattern=r"^DATASET-[A-Z0-9]{12}$")
    model_provider: str | None = Field(
        default=None, pattern=r"^(ollama|copilot)$")
    model_name: str | None = None
    adapters: list[str] = Field(default_factory=lambda: [
                                "native", "vally", "waza"])
    verbose_logging: bool = False
