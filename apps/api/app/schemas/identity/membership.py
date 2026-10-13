from pydantic import BaseModel, Field


class MembershipCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    role: str = Field(default="viewer",
                      pattern="^(viewer|developer|reviewer|admin)$")


class MembershipRoleUpdate(BaseModel):
    role: str = Field(pattern="^(viewer|developer|reviewer|admin)$")
