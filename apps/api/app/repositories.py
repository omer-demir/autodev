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
from .github_auth import github_credentials
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


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if github_credentials.token:
        headers["Authorization"] = f"Bearer {github_credentials.token}"
    return headers


def _repository_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "full_name": item["full_name"],
        "private": item["private"],
        "clone_url": item["clone_url"],
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


async def get_github_repository(value: str) -> dict[str, Any]:
    owner, repository = parse_github_url(value)
    endpoint = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repository, safe='')}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(endpoint, headers=_github_headers())
    if response.status_code == 404:
        raise RepositoryError(
            "GitHub repository was not found or is not accessible")
    response.raise_for_status()
    return _repository_payload(response.json())


async def list_github_repositories(owner: str) -> list[dict[str, Any]]:
    token = github_credentials.token
    endpoint = "https://api.github.com/user/repos" if token else f"https://api.github.com/users/{owner}/repos"
    params: dict[str, str | int] = {"per_page": 100, "sort": "updated"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(endpoint, headers=_github_headers(), params=params)
        if response.status_code == 404:
            raise RepositoryError(f"GitHub account not found: {owner}")
        response.raise_for_status()
        repositories = response.json()
    repositories = [
        item for item in repositories
        if item["owner"]["login"].casefold() == owner.casefold()
    ]
    return [_repository_payload(item) for item in repositories]


def _run_git(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=env, text=True, capture_output=True, timeout=180,
        check=False,
    )
    if result.returncode:
        message = result.stderr.strip().replace(
            github_credentials.token or "__never__", "***")
        raise RepositoryError(message or "Git operation failed")
    return result.stdout.strip()


def _clone_github(url: str, destination: Path, branch: str | None) -> None:
    token = github_credentials.token
    command = ["clone", "--no-tags"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([url, str(destination)])
    if not token:
        _run_git(command)
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
        _run_git(command, env=env)


def _materialize(project: Project, task_id: str) -> Path:
    root = Path(get_settings().workspace_dir).resolve() / task_id
    destination = root / "repo"
    if destination.exists():
        return destination
    root.mkdir(parents=True, exist_ok=True)
    if project.source_type == "github":
        if not project.repository_url:
            raise RepositoryError("GitHub project has no clone URL")
        _clone_github(project.repository_url,
                      destination, project.default_branch)
    else:
        source = validate_local_repository(project.repository_path)
        _run_git(["clone", "--no-hardlinks", str(source), str(destination)])
    branch = f"workbench/{task_id.lower()}"
    _run_git(["checkout", "-b", branch], cwd=destination)
    return destination


async def materialize_repository(project: Project, task_id: str) -> Path:
    return await asyncio.to_thread(_materialize, project, task_id)


def _publish(project: Project, workspace: Path, branch: str) -> dict[str, str]:
    if _run_git(["status", "--porcelain"], cwd=workspace):
        raise RepositoryError("Workspace must be clean before publishing")
    _run_git(["branch", "-M", branch], cwd=workspace)
    token = github_credentials.token
    if not token:
        _run_git(["push", "--set-upstream", "origin", branch], cwd=workspace)
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
    return {
        "branch": branch,
        "commit": _run_git(["rev-parse", "HEAD"], cwd=workspace),
        "remote": "origin",
    }


async def publish_repository(project: Project, workspace: Path, branch: str) -> dict[str, str]:
    return await asyncio.to_thread(_publish, project, workspace, branch)


async def create_github_pull_request(
    project: Project, branch: str, title: str, body: str
) -> dict[str, Any]:
    if project.source_type != "github" or not project.repository_url:
        raise RepositoryError("Pull requests require a GitHub-backed project")
    if not github_credentials.token:
        raise RepositoryError(
            "GitHub authentication is required to create a pull request")
    owner, repository = parse_github_url(project.repository_url)
    endpoint = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repository, safe='')}/pulls"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            endpoint,
            headers=_github_headers(),
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
    return {
        "number": value.get("number"),
        "url": value.get("html_url"),
        "state": value.get("state"),
    }


def remove_workspace(path: str | None) -> None:
    if not path:
        return
    workspace = Path(path).resolve()
    root = Path(get_settings().workspace_dir).resolve()
    if root in workspace.parents:
        shutil.rmtree(workspace.parent, ignore_errors=True)
