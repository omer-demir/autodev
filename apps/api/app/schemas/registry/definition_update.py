from pydantic import BaseModel, Field


class RegistryDefinitionUpdate(BaseModel):
    raw: str = Field(min_length=3, max_length=100_000)
