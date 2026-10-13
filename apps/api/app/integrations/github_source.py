from urllib.parse import quote, urlparse

import httpx

from ..github_auth import github_credentials
from ..registry import RegistryError


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_credentials.token:
        headers["Authorization"] = f"Bearer {github_credentials.token}"
    return headers


async def skills_sh_source(url: str, client: httpx.AsyncClient) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) != 3:
        raise RegistryError(
            "skills.sh URL must be https://skills.sh/<owner>/<repo>/<skill>")
    owner, repository, skill = parts
    api_root = f"https://api.github.com/repos/{quote(owner)}/{quote(repository)}"
    response = await client.get(api_root, headers=github_headers())
    if response.status_code != 200:
        raise RegistryError(
            "The skills.sh source repository could not be read")
    branch = str(response.json().get("default_branch") or "main")
    tree = await client.get(
        f"{api_root}/git/trees/{quote(branch)}?recursive=1",
        headers=github_headers(),
    )
    if tree.status_code != 200:
        raise RegistryError("The skills.sh source tree could not be read")
    suffix = f"/{skill}/SKILL.md"
    matches = [
        str(item.get("path"))
        for item in tree.json().get("tree", [])
        if str(item.get("path", "")).endswith(suffix)
        or str(item.get("path")) == f"{skill}/SKILL.md"
    ]
    if len(matches) != 1:
        raise RegistryError(
            f"Expected one SKILL.md for {skill}, found {len(matches)}")
    return f"https://raw.githubusercontent.com/{owner}/{repository}/{branch}/{matches[0]}"


def github_raw_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname == "github.com" and len(parts) >= 5 and parts[2] == "blob":
        owner, repository, _, branch, *path = parts
        return f"https://raw.githubusercontent.com/{owner}/{repository}/{branch}/{'/'.join(path)}"
    return url
