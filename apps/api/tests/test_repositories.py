import asyncio
import json
import subprocess
from unittest.mock import patch

import httpx
import pytest

from app.github_auth import GitHubCredentialStore, GitHubIdentity
from app.models import Project
from app.repositories import (
    RepositoryError,
    create_github_pull_request,
    parse_github_url,
    publish_repository,
)


async def run_git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        ["git", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def test_parse_public_github_repository_url():
    assert parse_github_url("https://github.com/octocat/Hello-World") == (
        "octocat",
        "Hello-World",
    )
    assert parse_github_url("https://github.com/octocat/Hello-World.git") == (
        "octocat",
        "Hello-World",
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://github.com/owner/repo",
        "https://example.com/github.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo?token=secret",
    ],
)
def test_parse_github_url_rejects_unsafe_or_non_repository_urls(value: str):
    with pytest.raises(RepositoryError):
        parse_github_url(value)


def test_oauth_state_is_single_use():
    credentials = GitHubCredentialStore()
    state = credentials.create_state()

    assert credentials.consume_state(state)
    assert not credentials.consume_state(state)


@pytest.mark.asyncio
async def test_publish_repository_pushes_clean_workspace(tmp_path):
    remote = tmp_path / "remote.git"
    workspace = tmp_path / "workspace"
    await run_git("init", "--bare", str(remote))
    await run_git("clone", str(remote), str(workspace))
    (workspace / "README.md").write_text("# Published\n", encoding="utf-8")
    await run_git("-C", str(workspace), "add", ".")
    await run_git(
        "-C", str(workspace), "-c", "user.name=Test",
        "-c", "user.email=test@example.com", "commit", "-m", "publish",
    )

    result = await publish_repository(
        Project(name="Local", repository_path=str(workspace)),
        workspace,
        "feature/published",
    )

    remote_revision = (
        await run_git(
            "--git-dir", str(remote), "rev-parse", "refs/heads/feature/published"
        )
    ).stdout.strip()
    assert result == {
        "branch": "feature/published",
        "commit": remote_revision,
        "remote": "origin",
    }

    (workspace / "dirty.txt").write_text("not committed", encoding="utf-8")
    with pytest.raises(RepositoryError, match="must be clean"):
        await publish_repository(
            Project(name="Local", repository_path=str(workspace)),
            workspace,
            "feature/dirty",
        )


@pytest.mark.asyncio
async def test_create_github_pull_request_uses_scoped_repository_endpoint():
    request: httpx.Request | None = None

    async def handler(value: httpx.Request) -> httpx.Response:
        nonlocal request
        request = value
        return httpx.Response(
            201,
            json={
                "number": 17, "html_url": "https://github.com/acme/repo/pull/17", "state": "open"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with (
        patch(
            "app.repositories.github_credentials._identity",
            GitHubIdentity(login="octocat", token="secret"),
        ),
        patch("app.repositories.httpx.AsyncClient", return_value=client),
    ):
        result = await create_github_pull_request(
            Project(
                name="GitHub",
                source_type="github",
                repository_url="https://github.com/acme/repo",
                default_branch="main",
            ),
            "feature/published",
            "Publish change",
            "Governed change",
        )

    assert result == {
        "number": 17,
        "url": "https://github.com/acme/repo/pull/17",
        "state": "open",
    }
    assert request is not None
    assert request.url.path == "/repos/acme/repo/pulls"
    assert request.headers["authorization"] == "Bearer secret"
    assert json.loads(request.content) == {
        "title": "Publish change",
        "head": "feature/published",
        "base": "main",
        "body": "Governed change",
    }
