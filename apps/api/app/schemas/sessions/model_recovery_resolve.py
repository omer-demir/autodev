from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ModelRecoveryResolve(BaseModel):
    action: Literal["retry", "change_model", "fallback", "cancel"]
    model: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_changed_model(self):
        if self.action == "change_model" and not self.model:
            raise ValueError("model is required when changing model")
        return self
