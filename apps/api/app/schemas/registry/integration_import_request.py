from typing import Literal

from pydantic import BaseModel, Field


class IntegrationImportRequest(BaseModel):
    url: str = Field(min_length=12, max_length=1000)
    kind: Literal["auto", "agent", "skill"] = "auto"
    identifier: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$",
    )
