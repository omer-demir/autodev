import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any

from copilot import CopilotClient, RuntimeConnection

from ..config import get_settings
from .normalization import model_dict

_MODEL_CACHE_SECONDS = 300.0
_copilot_model_cache: tuple[float, list[dict[str, Any]]] | None = None
_copilot_model_lock = asyncio.Lock()


async def copilot_models() -> list[dict[str, Any]]:
    global _copilot_model_cache
    if _copilot_model_cache and time.monotonic() - _copilot_model_cache[0] < _MODEL_CACHE_SECONDS:
        return [dict(item) for item in _copilot_model_cache[1]]
    async with _copilot_model_lock:
        if _copilot_model_cache and time.monotonic() - _copilot_model_cache[0] < _MODEL_CACHE_SECONDS:
            return [dict(item) for item in _copilot_model_cache[1]]
        settings = get_settings()
        token = os.getenv("COPILOT_GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        cli_path = shutil.which(settings.copilot_cli_path)
        if not cli_path:
            raise RuntimeError(
                f"GitHub Copilot CLI '{settings.copilot_cli_path}' is not available to the API."
            )
        options: dict[str, Any] = {
            "connection": RuntimeConnection.for_stdio(path=cli_path),
            "base_directory": str(Path(settings.copilot_home).expanduser().resolve()),
        }
        if token:
            options["github_token"] = token
            options["use_logged_in_user"] = False
        try:
            async with asyncio.timeout(settings.runtime_discovery_timeout_seconds):
                async with CopilotClient(**options) as client:
                    auth = await client.get_auth_status()
                    if not auth.isAuthenticated:
                        raise RuntimeError(
                            "GitHub Copilot is not authenticated. Run `copilot login` using "
                            f"COPILOT_HOME={options['base_directory']} or set COPILOT_GITHUB_TOKEN."
                        )
                    models = [model_dict(item) for item in await client.list_models()]
                    _copilot_model_cache = (time.monotonic(), models)
                    return [dict(item) for item in models]
        except TimeoutError as exc:
            raise RuntimeError(
                "GitHub Copilot model discovery timed out after "
                f"{settings.runtime_discovery_timeout_seconds} seconds."
            ) from exc
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "GitHub Copilot is unavailable. Sign in with Copilot CLI in COPILOT_HOME "
                "or set COPILOT_GITHUB_TOKEN to a token with Copilot access."
            ) from exc
