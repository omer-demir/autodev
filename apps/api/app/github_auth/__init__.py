from .identity import GitHubIdentity
from .store import GitHubCredentialStore

github_credentials = GitHubCredentialStore()

__all__ = ["GitHubCredentialStore", "GitHubIdentity", "github_credentials"]
