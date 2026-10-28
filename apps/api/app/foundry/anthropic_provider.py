import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .api_error import FoundryApiError

_FOUNDRY_SCOPE = "https://ai.azure.com/.default"
_ANTHROPIC_VERSION = "2023-06-01"


class FoundryAnthropicProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        token_provider: Callable[[], Awaitable[str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized = endpoint.rstrip("/")
        if not normalized.startswith("https://"):
            raise RuntimeError("Microsoft Foundry Anthropic endpoint must use HTTPS")
        if normalized.endswith("/v1/messages"):
            self.endpoint = normalized
        elif normalized.endswith("/anthropic"):
            self.endpoint = f"{normalized}/v1/messages"
        else:
            raise RuntimeError(
                "Microsoft Foundry Anthropic endpoint must end with "
                "/anthropic or /anthropic/v1/messages"
            )
        self.model = model
        self._token_provider = token_provider or self._azure_token
        self._client = client

    async def _azure_token(self) -> str:
        try:
            from azure.identity.aio import DefaultAzureCredential
        except ImportError as exc:
            raise RuntimeError(
                "Microsoft Foundry is configured but azure-identity is not installed"
            ) from exc
        credential = DefaultAzureCredential()
        try:
            token = await credential.get_token(_FOUNDRY_SCOPE)
        finally:
            await credential.close()
        if not token.token:
            raise RuntimeError("Unable to acquire a Microsoft Foundry token")
        return token.token

    async def run(
        self,
        *,
        instructions: str,
        messages: list[dict[str, Any]],
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        token = await self._token_provider()
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
            "stream": on_text_delta is not None,
        }
        if instructions.strip():
            body["system"] = instructions
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
        }

        if self._client:
            return await self._send(
                self._client, body, headers, on_text_delta
            )
        async with httpx.AsyncClient(timeout=300) as client:
            return await self._send(client, body, headers, on_text_delta)

    async def _send(
        self,
        client: httpx.AsyncClient,
        body: dict[str, Any],
        headers: dict[str, str],
        on_text_delta: Callable[[str], Awaitable[None]] | None,
    ) -> dict[str, Any]:
        request = client.build_request(
            "POST",
            self.endpoint,
            headers=headers,
            json=body,
        )
        response = await client.send(
            request, stream=on_text_delta is not None
        )
        try:
            if response.is_error:
                await response.aread()
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                raise _anthropic_error(response.status_code, payload)

            if on_text_delta is None:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise FoundryApiError(
                        response.status_code,
                        "invalid_response",
                        "Microsoft Foundry returned an invalid Anthropic response",
                    ) from exc
                if not isinstance(payload, dict):
                    raise FoundryApiError(
                        response.status_code,
                        "invalid_response",
                        "Microsoft Foundry returned an invalid Anthropic response",
                    )
                return payload

            if "text/event-stream" not in response.headers.get(
                "content-type", ""
            ).casefold():
                await response.aread()
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise FoundryApiError(
                        response.status_code,
                        "invalid_response",
                        "Microsoft Foundry returned an invalid Anthropic response",
                    ) from exc
                if not isinstance(payload, dict):
                    raise FoundryApiError(
                        response.status_code,
                        "invalid_response",
                        "Microsoft Foundry returned an invalid Anthropic response",
                    )
                text = _response_text(payload)
                if text:
                    await on_text_delta(text)
                return payload

            text_parts: list[str] = []
            result: dict[str, Any] = {
                "id": "",
                "model": self.model,
                "content": [],
                "usage": {},
            }
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    raw = line[5:].lstrip()
                    if raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except ValueError as exc:
                        raise FoundryApiError(
                            response.status_code,
                            "invalid_stream",
                            "Microsoft Foundry returned an invalid Anthropic stream event",
                        ) from exc
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("type")
                    if event_type == "message_start":
                        message = event.get("message")
                        if isinstance(message, dict):
                            result["id"] = message.get("id", "")
                            result["model"] = message.get("model", self.model)
                            result["usage"].update(
                                _anthropic_usage(message.get("usage"))
                            )
                    elif event_type == "content_block_delta":
                        delta = event.get("delta")
                        text = (
                            delta.get("text")
                            if isinstance(delta, dict)
                            and delta.get("type") == "text_delta"
                            else None
                        )
                        if isinstance(text, str) and text:
                            text_parts.append(text)
                            await on_text_delta(text)
                    elif event_type == "message_delta":
                        result["usage"].update(
                            _anthropic_usage(event.get("usage"))
                        )
                    elif event_type == "error":
                        raise _anthropic_error(
                            502, {"error": event.get("error", {})}
                        )
            text = "".join(text_parts)
            result["content"] = [{"type": "text", "text": text}] if text else []
            return result
        finally:
            await response.aclose()


def _anthropic_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    usage: dict[str, int] = {}
    for source, target in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("cache_read_input_tokens", "cache_read_input_tokens"),
        ("cache_creation_input_tokens", "cache_creation_input_tokens"),
    ):
        count = value.get(source)
        if isinstance(count, int) and not isinstance(count, bool):
            usage[target] = count
    return usage


def _response_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    return "".join(
        str(item.get("text") or "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    )


def _anthropic_error(status_code: int, payload: Any) -> FoundryApiError:
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {}
    code = str(error.get("type") or "provider_error")
    message = " ".join(str(error.get("message") or "").split())[:500]
    detail = f": {message}" if message else ""
    return FoundryApiError(
        status_code,
        code,
        f"Microsoft Foundry Anthropic request failed with HTTP "
        f"{status_code} ({code}){detail}",
    )
