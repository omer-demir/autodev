from pydantic import BaseModel, Field


class TerminalCommand(BaseModel):
    command: str = Field(min_length=1, max_length=500)
