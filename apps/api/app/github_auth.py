import secrets
import time
from dataclasses import dataclass

from .config import get_settings


@dataclass(frozen=True)
class GitHubIdentity:
    login: str
    token: str


class GitHubCredentialStore:
    """Process-local credentials for the single-user local workbench."""

    def __init__(self) -> None:
        self._identity: GitHubIdentity | None = None
        self._states: dict[str, float] = {}

    @property
    def token(self) -> str | None:
        return self._identity.token if self._identity else get_settings().github_token

    @property
    def login(self) -> str | None:
        return self._identity.login if self._identity else None

    @property
    def method(self) -> str | None:
        if self._identity:
            return "oauth"
        if get_settings().github_token:
            return "environment"
        return None

    def create_state(self) -> str:
        now = time.monotonic()
        self._states = {
            state: expires for state, expires in self._states.items() if expires > now
        }
        state = secrets.token_urlsafe(32)
        self._states[state] = now + 600
        return state

    def consume_state(self, state: str) -> bool:
        expires = self._states.pop(state, 0)
        return expires > time.monotonic()

    def connect(self, login: str, token: str) -> None:
        self._identity = GitHubIdentity(login=login, token=token)

    def disconnect(self) -> None:
        self._identity = None


github_credentials = GitHubCredentialStore()
