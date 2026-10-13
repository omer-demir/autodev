import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from .config import get_settings
from .github_auth import GitHubIdentity, github_credentials
from .models import Project


class RepositoryError(RuntimeError):
    pass


def validate_local_repository(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise RepositoryError(f"Local repository does not exist: {path}")
    if not (path / ".git").exists():
        raise RepositoryError(f"Local path is not a Git repository: {path}")
    return path


def _github_headers(token: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _repository_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "full_name": item["full_name"],
        "private": item["private"],
        "clone_url": item["clone_url"],
        "ssh_url": item.get("ssh_url"),
        "html_url": item.get("html_url"),
        "owner": (item.get("owner") or {}).get("login"),
        "default_branch": item["default_branch"],
        "updated_at": item["updated_at"],
    }


def parse_github_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RepositoryError(
            "Use a full HTTPS GitHub URL such as https://github.com/owner/repository")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise RepositoryError("GitHub URL must identify one repository")
    owner, repository = parts
    repository = repository.removesuffix(".git")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")
    if not owner or not repository or not set(owner) <= allowed or not set(repository) <= allowed:
        raise RepositoryError(
            "GitHub owner or repository name contains unsupported characters")
    return owner, repository


def validate_publication(project: Project, create_pull_request: bool) -> None:
    if not create_pull_request:
        return
    if project.source_type != "github" or not project.repository_url:
        raise RepositoryError("Pull requests require a GitHub-backed project")
    owner, _ = parse_github_url(project.repository_url)
    if (
        not github_credentials.get_installation(
            project.organization_id,
            project.created_by,
            owner,
            project.connector_id,
        )
        and not github_credentials.get_token(
            project.organization_id, project.created_by
        )
    ):
        raise RepositoryError(
            "GitHub API authentication is required to create a pull request. "
            "Disable pull request creation to push with SSH, or connect GitHub "
            "or configure WORKBENCH_GITHUB_TOKEN."
        )


async def get_github_repository(
    value: str,
    organization_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    owner, repository = parse_github_url(value)
    endpoint = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repository, safe='')}"
    identity = (
        await github_credentials.identity_for_repository(
            organization_id, owner_id, owner, repository
        )
        if organization_id
        else None
    )
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        token = identity.token if identity else github_credentials.token
        response = await client.get(endpoint, headers=_github_headers(token))
    if response.status_code == 404:
        raise RepositoryError(
            "GitHub repository was not found or is not accessible")
    response.raise_for_status()
    return _repository_payload(response.json())


async def list_github_repositories(
    owner: str,
    organization_id: str | None = None,
    owner_id: str | None = None,
    connector_id: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    identity = (
        await github_credentials.installation_identity(
            organization_id, owner_id, owner, connector_id=connector_id
        )
        if organization_id
        else None
    )
    token = (
        identity.token
        if identity
        else github_credentials.get_token(organization_id, owner_id)
        if organization_id
        else github_credentials.token
    )
    endpoint = (
        "https://api.github.com/installation/repositories"
        if identity and identity.method == "github_app"
        else "https://api.github.com/user/repos"
        if token
        else f"https://api.github.com/users/{owner}/repos"
    )
    params: dict[str, str | int] = {"per_page": 100, "sort": "updated"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(endpoint, headers=_github_headers(token), params=params)
        if response.status_code == 404:
            raise RepositoryError(f"GitHub account not found: {owner}")
        response.raise_for_status()
        value = response.json()
        repositories = value.get("repositories", []) if isinstance(value, dict) else value
    repositories = [
        item for item in repositories
        if item["owner"]["login"].casefold() == owner.casefold()
        and (
            not query
            or query.casefold() in str(item.get("name") or "").casefold()
            or query.casefold() in str(item.get("full_name") or "").casefold()
        )
    ]
    return [_repository_payload(item) for item in repositories]


def _run_git(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=env, text=True, capture_output=True, timeout=180,
        check=False,
    )
    if result.returncode:
        sensitive = (env or {}).get("GITHUB_TOKEN") or github_credentials.token
        message = result.stderr.strip().replace(sensitive or "__never__", "***")
        raise RepositoryError(message or "Git operation failed")
    return result.stdout.strip()


def _clone_github(
    url: str,
    destination: Path,
    branch: str | None,
    token: str | None,
) -> None:
    command = ["clone", "--no-tags"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([url, str(destination)])

    def clone(env: dict[str, str] | None = None) -> None:
        try:
            _run_git(command, env=env)
        except RepositoryError as clone_error:
            if not branch:
                raise
            try:
                remote_refs = _run_git(["ls-remote", url], env=env)
            except RepositoryError:
                raise clone_error
            if remote_refs:
                raise
            shutil.rmtree(destination, ignore_errors=True)
            _run_git(["clone", "--no-tags", url, str(destination)], env=env)

    if not token:
        env = None
        if url.startswith("git@"):
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
        clone(env)
        return
    with tempfile.TemporaryDirectory() as directory:
        askpass = Path(directory) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\ncase \"$1\" in *Username*) echo x-access-token;; *) echo \"$GITHUB_TOKEN\";; esac\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        env = os.environ.copy()
        env.update({"GIT_ASKPASS": str(
            askpass), "GIT_TERMINAL_PROMPT": "0", "GITHUB_TOKEN": token})
        clone(env)


def _materialize(project: Project, task_id: str, token: str | None = None) -> Path:
    root = Path(get_settings().workspace_dir).resolve() / task_id
    destination = root / "repo"
    if destination.exists():
        return destination
    root.mkdir(parents=True, exist_ok=True)
    if project.source_type == "empty":
        branch = f"workbench/{task_id.lower()}"
        destination.mkdir(parents=True)
        _run_git(["init", "--initial-branch", branch, str(destination)])
        return destination
    if project.source_type == "github":
        if not project.repository_url:
            raise RepositoryError("GitHub project has no clone URL")
        clone_url = project.repository_url
        if project.transport == "ssh":
            owner, repository = parse_github_url(project.repository_url)
            clone_url = f"git@github.com:{owner}/{repository}.git"
            token = None
        _clone_github(clone_url, destination, project.default_branch, token)
    else:
        source = validate_local_repository(project.repository_path)
        _run_git(["clone", "--no-hardlinks", str(source), str(destination)])
    branch = f"workbench/{task_id.lower()}"
    _run_git(["checkout", "-b", branch], cwd=destination)
    return destination


async def materialize_repository(project: Project, task_id: str) -> Path:
    token = None
    if project.source_type == "github" and project.repository_url:
        if urlparse(project.repository_url).hostname == "github.com":
            owner, repository = parse_github_url(project.repository_url)
            try:
                identity_options = (
                    {"connector_id": project.connector_id}
                    if project.connector_id
                    else {}
                )
                identity = await github_credentials.identity_for_repository(
                    project.organization_id,
                    project.created_by,
                    owner,
                    repository,
                    **identity_options,
                )
            except (httpx.HTTPError, RuntimeError) as exc:
                raise RepositoryError(
                    f"GitHub App authentication failed: {exc}"
                ) from exc
            token = identity.token if identity else None
        else:
            token = github_credentials.get_token(
                project.organization_id, project.created_by
            )
    return await asyncio.to_thread(_materialize, project, task_id, token)


def _publish(
    project: Project,
    workspace: Path,
    branch: str,
    identity: GitHubIdentity | None = None,
) -> dict[str, Any]:
    if _run_git(["status", "--porcelain"], cwd=workspace):
        raise RepositoryError("Workspace must be clean before publishing")
    _run_git(["branch", "-M", branch], cwd=workspace)
    token = identity.token if identity and project.transport != "ssh" else None
    if not token:
        env = None
        if project.source_type == "github":
            if not project.repository_url:
                raise RepositoryError("GitHub project has no repository URL")
            owner, repository = parse_github_url(project.repository_url)
            ssh_url = f"git@github.com:{owner}/{repository}.git"
            _run_git(
                ["remote", "set-url", "--push", "origin", ssh_url],
                cwd=workspace,
            )
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
        _run_git(
            ["push", "--set-upstream", "origin", branch],
            cwd=workspace,
            env=env,
        )
    else:
        with tempfile.TemporaryDirectory() as directory:
            askpass = Path(directory) / "askpass.sh"
            askpass.write_text(
                "#!/bin/sh\ncase \"$1\" in *Username*) echo x-access-token;; "
                "*) echo \"$GITHUB_TOKEN\";; esac\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            env = os.environ.copy()
            env.update({
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "GITHUB_TOKEN": token,
            })
            _run_git(["push", "--set-upstream", "origin", branch],
                     cwd=workspace, env=env)
    result: dict[str, Any] = {
        "branch": branch,
        "commit": _run_git(["rev-parse", "HEAD"], cwd=workspace),
        "remote": "origin",
    }
    if identity and token:
        result.update({
            "github_actor": identity.login,
            "github_auth_method": identity.method,
            "github_installation_id": identity.installation_id,
        })
    return result


async def publish_repository(
    project: Project, workspace: Path, branch: str
) -> dict[str, Any]:
    identity = None
    if project.source_type == "github" and project.repository_url:
        owner, repository = parse_github_url(project.repository_url)
        try:
            identity_options = (
                {"connector_id": project.connector_id}
                if project.connector_id
                else {}
            )
            identity = await github_credentials.identity_for_repository(
                project.organization_id,
                project.created_by,
                owner,
                repository,
                write=True,
                **identity_options,
            )
        except (httpx.HTTPError, RuntimeError) as exc:
            raise RepositoryError(f"GitHub App authentication failed: {exc}") from exc
    return await asyncio.to_thread(_publish, project, workspace, branch, identity)


async def create_github_pull_request(
    project: Project, branch: str, title: str, body: str
) -> dict[str, Any]:
    validate_publication(project, True)
    assert project.repository_url is not None
    owner, repository = parse_github_url(project.repository_url)
    try:
        identity_options = (
            {"connector_id": project.connector_id}
            if project.connector_id
            else {}
        )
        identity = await github_credentials.identity_for_repository(
            project.organization_id,
            project.created_by,
            owner,
            repository,
            write=True,
            **identity_options,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise RepositoryError(f"GitHub App authentication failed: {exc}") from exc
    if not identity:
        raise RepositoryError("GitHub authentication is required to create a pull request")
    endpoint = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repository, safe='')}/pulls"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            endpoint,
            headers=_github_headers(identity.token),
            json={
                "title": title,
                "head": branch,
                "base": project.default_branch or "main",
                "body": body,
            },
        )
    if response.status_code not in {200, 201}:
        raise RepositoryError(
            f"GitHub pull request creation failed: HTTP {response.status_code}"
        )
    value = response.json()
    result = {
        "number": value.get("number"),
        "url": value.get("html_url"),
        "state": value.get("state"),
    }
    if identity.method == "github_app":
        result.update({
            "github_actor": identity.login,
            "github_auth_method": identity.method,
            "github_installation_id": identity.installation_id,
        })
    return result


def remove_workspace(path: str | None) -> None:
    if not path:
        return
    workspace = Path(path).resolve()
    root = Path(get_settings().workspace_dir).resolve()
    if root in workspace.parents:
        shutil.rmtree(workspace.parent, ignore_errors=True)


def remove_task_workspace(task_id: str) -> None:
    root = Path(get_settings().workspace_dir).resolve()
    workspace = (root / task_id).resolve()
    if root in workspace.parents:
        shutil.rmtree(workspace, ignore_errors=True)
