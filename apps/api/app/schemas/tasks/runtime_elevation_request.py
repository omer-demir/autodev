from typing import Literal

from pydantic import BaseModel, Field


class RuntimeElevationRequest(BaseModel):
    target_tier: Literal[1, 2]
    ttl_seconds: int = Field(default=300, ge=1, le=3600)
    reason: str = Field(min_length=3, max_length=500)
    attestation: str | None = Field(
        default=None, min_length=3, max_length=1000)
