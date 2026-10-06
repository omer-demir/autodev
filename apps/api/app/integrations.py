import ipaddress
import re
import socket
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import quote, urlparse

import httpx
import yaml

from .github_auth import github_credentials
from .registry import IDENTIFIER, RegistryError, save_definition


ImportKind = Literal["auto", "agent", "skill"]
_SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MAX_IMPORT_BYTES = 250_000


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:64] or "imported-agent"


def _markdown(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        raise RegistryError(
            "Imported Markdown must start with YAML frontmatter")
    try:
        frontmatter, body = raw[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(frontmatter) or {}
    except (ValueError, yaml.YAMLError) as exc:
        raise RegistryError(
            "Imported Markdown has invalid YAML frontmatter") from exc
    if not isinstance(metadata, dict) or not body.strip():
        raise RegistryError(
            "Imported Markdown requires metadata and instructions")
    return metadata, body.strip()


def _version(metadata: dict[str, Any]) -> str:
    nested = metadata.get("metadata")
    candidate = nested.get("version") if isinstance(nested, dict) else None
    return str(candidate or metadata.get("version") or "0.1.0")


def normalize_external_definition(
    source_url: str,
    raw: str,
    *,
    kind: ImportKind = "auto",
    identifier: str | None = None,
) -> tuple[str, str, str]:
    metadata, instructions = _markdown(raw)
    inferred = "skill" if PurePosixPath(
        urlparse(source_url).path).name == "SKILL.md" else "agent"
    selected = inferred if kind == "auto" else kind
    if selected == "skill":
        name = str(metadata.get("name") or "")
        if not _SKILL_NAME.fullmatch(name):
            raise RegistryError(
                "Skill name must use lowercase letters, numbers, and hyphens")
        skill_id = identifier or name
        if not _SKILL_NAME.fullmatch(skill_id):
            raise RegistryError(
                "Local skill ID must use lowercase letters, numbers, and hyphens")
        data = {
            "name": name,
            "version": _version(metadata),
            "description": str(metadata.get("description") or "Imported Agent Skill"),
            "instructions": instructions,
            "source": {
                "url": source_url,
                "format": "agent-skills",
                "license": metadata.get("license"),
                "compatibility": metadata.get("compatibility"),
                "declared_allowed_tools": metadata.get("allowed-tools"),
                "trust": "unreviewed",
            },
        }
        return "skills", skill_id, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    display_name = str(metadata.get("name") or "Imported Agent")
    agent_id = identifier or _slug(display_name)
    if not IDENTIFIER.fullmatch(agent_id):
        raise RegistryError("Imported agent ID is invalid")
    handoffs = metadata.get("handoffs") if isinstance(
        metadata.get("handoffs"), list) else []
    declared_skills = sorted({
        str(item.get("prompt", "")).removeprefix("/")
        for item in handoffs if isinstance(item, dict) and str(item.get("prompt", "")).startswith("/")
    })
    data = {
        "name": display_name,
        "version": _version(metadata),
        "description": str(metadata.get("description") or "Imported agent"),
        "status": "draft",
        "identity": {"id": f"did:local:{agent_id}"},
        "policy": "development",
        "harness": {"id": "workspace", "version": "1.0.0"},
        "environment": {
            "image": "agentic-sdlc-sandbox:local",
            "network_mode": "none",
            "workspace_access": "read-only",
            "setup_instructions": "Inspect the repository using governed read tools.",
        },
        "model": {"provider": "copilot", "name": "auto"},
        "capabilities": ["repository.read", "git.status", "git.diff"],
        "mcp_servers": ["workspace"],
        "skills": [],
        "instructions": instructions,
        "approval": ["git.commit", "git.push"],
        "deny": ["repository.write", "dependency.install", "production.deploy", "host.credentials.read"],
        "source": {
            "url": source_url,
            "format": "github-copilot-agent",
            "declared_tools": metadata.get("tools"),
            "declared_skills": declared_skills,
            "trust": "unreviewed",
        },
    }
    return "agents", agent_id, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _validate_public_https(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RegistryError(
            "Import URL must be public HTTPS without embedded credentials")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RegistryError("Import host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise RegistryError(
                "Import URL must resolve only to public addresses")


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if github_credentials.token:
        headers["Authorization"] = f"Bearer {github_credentials.token}"
    return headers


async def _skills_sh_source(url: str, client: httpx.AsyncClient) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) != 3:
        raise RegistryError(
            "skills.sh URL must be https://skills.sh/<owner>/<repo>/<skill>")
    owner, repository, skill = parts
    api_root = f"https://api.github.com/repos/{quote(owner)}/{quote(repository)}"
    response = await client.get(api_root, headers=_github_headers())
    if response.status_code != 200:
        raise RegistryError(
            "The skills.sh source repository could not be read")
    branch = str(response.json().get("default_branch") or "main")
    tree = await client.get(f"{api_root}/git/trees/{quote(branch)}?recursive=1", headers=_github_headers())
    if tree.status_code != 200:
        raise RegistryError("The skills.sh source tree could not be read")
    suffix = f"/{skill}/SKILL.md"
    matches = [str(item.get("path")) for item in tree.json().get("tree", []) if str(
        item.get("path", "")).endswith(suffix) or str(item.get("path")) == f"{skill}/SKILL.md"]
    if len(matches) != 1:
        raise RegistryError(
            f"Expected one SKILL.md for {skill}, found {len(matches)}")
    return f"https://raw.githubusercontent.com/{owner}/{repository}/{branch}/{matches[0]}"


def _github_raw_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname == "github.com" and len(parts) >= 5 and parts[2] == "blob":
        owner, repository, _, branch, *path = parts
        return f"https://raw.githubusercontent.com/{owner}/{repository}/{branch}/{'/'.join(path)}"
    return url


async def fetch_external_markdown(url: str) -> tuple[str, str]:
    _validate_public_https(url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        resolved = await _skills_sh_source(url, client) if urlparse(url).hostname in {"skills.sh", "www.skills.sh"} else _github_raw_url(url)
        for _ in range(5):
            _validate_public_https(resolved)
            response = await client.get(resolved, headers={"Accept": "text/markdown"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise RegistryError(
                        "Import redirect omitted its destination")
                resolved = str(response.url.join(location))
                continue
            if response.status_code != 200:
                raise RegistryError(
                    f"Import source returned HTTP {response.status_code}")
            if len(response.content) > _MAX_IMPORT_BYTES:
                raise RegistryError("Import source exceeds 250000 bytes")
            return resolved, response.text
    raise RegistryError("Import source redirected too many times")


async def import_external_definition(
    url: str, *, kind: ImportKind = "auto", identifier: str | None = None
) -> dict[str, Any]:
    resolved, raw = await fetch_external_markdown(url)
    registry_kind, definition_id, normalized = normalize_external_definition(
        resolved, raw, kind=kind, identifier=identifier
    )
    return save_definition(registry_kind, definition_id, normalized)
