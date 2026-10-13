from pydantic import BaseModel, Field, field_validator


class PublishRequest(BaseModel):
    branch: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9._/-]+$",
    )
    create_pull_request: bool = False

    @field_validator("branch")
    @classmethod
    def validate_git_branch(cls, value: str) -> str:
        if (
            value[0] in "./"
            or value[-1] in "./"
            or ".." in value
            or "//" in value
            or "@{" in value
        ):
            raise ValueError("branch is not a valid Git reference name")
        return value
