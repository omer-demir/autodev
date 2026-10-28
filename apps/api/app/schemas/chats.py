from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatAttachmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    data: str = Field(min_length=1, max_length=14_000_000)


class ChatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=10000)
    title: str | None = Field(default=None, min_length=3, max_length=29)
    project_id: int | None = Field(default=None, gt=0)
    agent_ids: list[str] = Field(default_factory=list, max_length=5)
    skill_ids: list[str] = Field(default_factory=list, max_length=20)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_provider: str | None = Field(default=None, min_length=1, max_length=100)
    approval_strategy: Literal["agent_policy"] = "agent_policy"
    attachments: list[ChatAttachmentCreate] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def require_message_or_attachment(self) -> "ChatCreate":
        if not self.message.strip() and not self.attachments:
            raise ValueError("A message or attachment is required")
        if sum(len(item.data) for item in self.attachments) > 28_000_000:
            raise ValueError("Chat attachments must total 20 MiB or less")
        if self.project_id is not None and self.attachments:
            raise ValueError("Attachments are currently supported in repository-free chats")
        return self

    @field_validator("agent_ids")
    @classmethod
    def valid_unique_agents(cls, values: list[str]) -> list[str]:
        if any(
            not value.startswith("did:local:")
            or not value.removeprefix("did:local:")
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789._-"
                for character in value.removeprefix("did:local:")
            )
            for value in values
        ):
            raise ValueError("Agent IDs must be local agent DIDs")
        if len(set(values)) != len(values):
            raise ValueError("Agent IDs must be unique")
        return values

    @field_validator("skill_ids")
    @classmethod
    def valid_unique_skills(cls, values: list[str]) -> list[str]:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789._-"
        if any(not value or any(character not in allowed for character in value)
               for value in values):
            raise ValueError("Skill IDs must be valid registry identifiers")
        if len(set(values)) != len(values):
            raise ValueError("Skill IDs must be unique")
        return values


class ChatMessageCreate(BaseModel):
    content: str = Field(default="", max_length=10000)
    attachments: list[ChatAttachmentCreate] = Field(default_factory=list, max_length=4)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_provider: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "ChatMessageCreate":
        if not self.content.strip() and not self.attachments:
            raise ValueError("A message or attachment is required")
        if sum(len(item.data) for item in self.attachments) > 28_000_000:
            raise ValueError("Chat attachments must total 20 MiB or less")
        return self
