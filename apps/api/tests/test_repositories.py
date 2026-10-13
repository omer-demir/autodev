import asyncio
import json
import subprocess
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.github_auth import GitHubCredentialStore, GitHubIdentity
from app.models import Project
from app.repositories import (
    RepositoryError,
    create_github_pull_request,
    materialize_repository,
    parse_github_url,
    publish_repository,
    remove_task_workspace,
    validate_publication,
)


def test_remove_task_workspace_preserves_other_task_directories(tmp_path):
    removed = tmp_path / "TASK-REMOVE" / "repo"
    preserved = tmp_path / "TASK-KEEP" / "repo"
    removed.mkdir(parents=True)
    preserved.mkdir(parents=True)

    with patch("app.repositories.get_settings") as settings:
        settings.return_value.workspace_dir = str(tmp_path)
        remove_task_workspace("TASK-REMOVE")

    assert not removed.parent.exists()
    assert preserved.exists()


@pytest.mark.asyncio
async def test_materialize_empty_project_initializes_isolated_git_workspace(tmp_path):
    with patch("app.repositories.get_settings") as settings:
        settings.return_value.workspace_dir = str(tmp_path)
        workspace = await materialize_repository(
            Project(name="Discovery", source_type="empty", repository_path=""),
            "TASK-EMPTY",
        )

    assert workspace == tmp_path / "TASK-EMPTY" / "repo"
    assert (workspace / ".git").is_dir()
    branch = await run_git("-C", str(workspace), "branch", "--show-current")
    assert branch.stdout.strip() == "workbench/task-empty"


@pytest.mark.asyncio
async def test_materialize_github_project_with_no_commits(tmp_path):
    remote = tmp_path / "remote.git"
    await run_git("init", "--bare", "--initial-branch", "main", str(remote))

    with (
        patch("app.repositories.get_settings") as settings,
        patch("app.repositories.github_credentials.get_token", return_value=None),
    ):
        settings.return_value.workspace_dir = str(tmp_path / "workspaces")
        workspace = await materialize_repository(
            Project(
                name="Empty GitHub repository",
                source_type="github",
                repository_path="",
                repository_url=str(remote),
                default_branch="main",
            ),
            "TASK-EMPTY-GITHUB",
        )

    branch = await run_git("-C", str(workspace), "branch", "--show-current")
    assert branch.stdout.strip() == "workbench/task-empty-github"
    origin = await run_git("-C", str(workspace), "remote", "get-url", "origin")
    assert origin.stdout.strip() == str(remote)


@pytest.mark.asyncio
async def test_materialize_github_project_rejects_missing_branch_on_nonempty_remote(
    tmp_path,
):
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    source.mkdir()
    await run_git("init", "--initial-branch", "trunk", str(source))
    (source / "README.md").write_text("# Existing\n", encoding="utf-8")
    await run_git("-C", str(source), "add", ".")
    await run_git(
        "-C", str(source), "-c", "user.name=Test", "-c",
        "user.email=test@example.com", "commit", "-m", "initial",
    )
    await run_git("clone", "--bare", str(source), str(remote))

    with (
        patch("app.repositories.get_settings") as settings,
        patch("app.repositories.github_credentials.get_token", return_value=None),
    ):
        settings.return_value.workspace_dir = str(tmp_path / "workspaces")
        with pytest.raises(RepositoryError, match="Remote branch main not found"):
            await materialize_repository(
                Project(
                    name="Initialized GitHub repository",
                    source_type="github",
                    repository_path="",
                    repository_url=str(remote),
                    default_branch="main",
                ),
                "TASK-WRONG-BRANCH",
            )


@pytest.mark.asyncio
async def test_materialize_connector_repository_uses_selected_ssh_transport(tmp_path):
    project = Project(
        name="GitHub SSH",
        source_type="github",
        repository_path="",
        repository_url="https://github.com/acme/repository.git",
        default_branch="main",
        connector_id="CON-123",
        transport="ssh",
    )
    identity = GitHubIdentity(
        login="autodev[bot]",
        token="installation-token",
        method="github_app",
    )

    with (
        patch("app.repositories.get_settings") as settings,
        patch(
            "app.repositories.github_credentials.identity_for_repository",
            AsyncMock(return_value=identity),
        ) as credentials,
        patch("app.repositories._clone_github") as clone,
        patch("app.repositories._run_git", return_value=""),
    ):
        settings.return_value.workspace_dir = str(tmp_path)
        await materialize_repository(project, "TASK-SSH-CONNECTOR")

    credentials.assert_awaited_once_with(
        "local", None, "acme", "repository", connector_id="CON-123"
    )
    clone.assert_called_once_with(
        "git@github.com:acme/repository.git",
        tmp_path / "TASK-SSH-CONNECTOR" / "repo",
        "main",
        None,
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
async def test_publish_github_repository_uses_ssh_without_token(tmp_path):
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def run_git(
        args: list[str], cwd=None, env: dict[str, str] | None = None
    ) -> str:
        calls.append((args, env))
        return "revision" if args == ["rev-parse", "HEAD"] else ""

    project = Project(
        name="GitHub",
        source_type="github",
        repository_path="",
        repository_url="https://github.com/acme/repo",
    )
    with (
        patch("app.repositories._run_git", side_effect=run_git),
        patch("app.repositories.github_credentials.get_token", return_value=None),
    ):
        result = await publish_repository(project, tmp_path, "feature/ssh")

    assert result["commit"] == "revision"
    assert ([
        "remote", "set-url", "--push", "origin", "git@github.com:acme/repo.git"
    ], None) in calls
    push = next(item for item in calls if item[0][0] == "push")
    assert push[1] is not None
    assert push[1]["GIT_TERMINAL_PROMPT"] == "0"
    assert push[1]["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"


@pytest.mark.asyncio
async def test_publish_github_repository_prefers_installation_token(tmp_path):
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def run_git(
        args: list[str], cwd=None, env: dict[str, str] | None = None
    ) -> str:
        calls.append((args, env))
        return "revision" if args == ["rev-parse", "HEAD"] else ""

    identity = GitHubIdentity(
        login="autodev[bot]",
        token="installation-token",
        method="github_app",
        app_slug="autodev",
        installation_id=9876,
    )
    project = Project(
        name="GitHub",
        source_type="github",
        repository_path="",
        repository_url="https://github.com/acme/repo",
    )
    with (
        patch("app.repositories._run_git", side_effect=run_git),
        patch(
            "app.repositories.github_credentials.identity_for_repository",
            AsyncMock(return_value=identity),
        ) as credentials,
    ):
        result = await publish_repository(project, tmp_path, "feature/app")

    credentials.assert_awaited_once_with(
        "local", None, "acme", "repo", write=True
    )
    assert not any(call[0][:3] == ["remote", "set-url", "--push"]
                   for call in calls)
    push = next(item for item in calls if item[0][0] == "push")
    assert push[1] is not None
    assert push[1]["GITHUB_TOKEN"] == "installation-token"
    assert result == {
        "branch": "feature/app",
        "commit": "revision",
        "remote": "origin",
        "github_actor": "autodev[bot]",
        "github_auth_method": "github_app",
        "github_installation_id": 9876,
    }


def test_pull_request_publication_requires_api_authentication():
    project = Project(
        name="GitHub",
        source_type="github",
        repository_path="",
        repository_url="https://github.com/acme/repo",
    )
    with (
        patch("app.repositories.github_credentials.get_token", return_value=None),
        pytest.raises(RepositoryError, match="push with SSH"),
    ):
        validate_publication(project, True)


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
