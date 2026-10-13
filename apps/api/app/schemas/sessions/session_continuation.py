from pydantic import BaseModel, Field


class SessionContinuation(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    agent_id: str | None = Field(
        default=None,
        pattern=r"^did:local:[a-z0-9][a-z0-9._-]{0,99}$",
    )
