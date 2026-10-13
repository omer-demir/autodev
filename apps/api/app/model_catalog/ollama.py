from typing import Any

import httpx

from ..config import get_settings


async def ollama_models(*, fallback: bool = False) -> list[dict[str, Any]]:
    url = get_settings().ollama_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        return []
    return [
        {**item, "provider": "ollama", "fallback": fallback}
        for item in response.json().get("models", [])
    ]
