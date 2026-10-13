from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubIdentity:
    login: str
    token: str
    method: str = "oauth"
    app_slug: str | None = None
    installation_id: int | None = None
