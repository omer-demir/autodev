from typing import Any
from urllib.parse import urlparse

import httpx

from ..registry import RegistryError, save_definition
from .github_source import github_raw_url, skills_sh_source
from .normalization import ImportKind, normalize_external_definition
from .security import validate_public_https

_MAX_IMPORT_BYTES = 250_000


async def fetch_external_markdown(url: str) -> tuple[str, str]:
    validate_public_https(url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        resolved = (
            await skills_sh_source(url, client)
            if urlparse(url).hostname in {"skills.sh", "www.skills.sh"}
            else github_raw_url(url)
        )
        for _ in range(5):
            validate_public_https(resolved)
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
