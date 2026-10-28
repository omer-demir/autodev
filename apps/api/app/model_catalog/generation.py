import base64
import binascii
import mimetypes
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agent_framework import Message
from pathlib import Path

from agent_framework.github import GitHubCopilotAgent
from agent_framework.ollama import OllamaChatClient

from ..config import get_settings
from ..foundry.anthropic_provider import FoundryAnthropicProvider
from ..foundry.provider import FoundryResponsesProvider


@dataclass(frozen=True)
class ChatUsage:
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def _token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _foundry_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        contents: list[dict[str, Any]] = []
        for item in message.contents:
            if item.type == "text":
                contents.append({
                    "type": (
                        "output_text"
                        if message.role == "assistant"
                        else "input_text"
                    ),
                    "text": item.text,
                })
                continue
            if item.type != "data" or not item.uri or not item.media_type:
                continue
            if not item.uri.startswith("data:") or ";base64," not in item.uri:
                raise ValueError("Chat attachments must use base64 data URIs")
            data = item.uri.split(";base64,", 1)[1]
            if item.media_type.startswith("image/"):
                contents.append({
                    "type": "input_image",
                    "image_url": item.uri,
                })
            elif item.media_type.startswith("audio/"):
                audio_format = {
                    "audio/mpeg": "mp3",
                    "audio/mp3": "mp3",
                    "audio/mp4": "m4a",
                    "audio/wav": "wav",
                    "audio/x-wav": "wav",
                    "audio/webm": "webm",
                    "audio/ogg": "ogg",
                    "audio/flac": "flac",
                }.get(item.media_type)
                if not audio_format:
                    raise ValueError(
                        f"Microsoft Foundry chat does not support audio type {item.media_type}"
                    )
                contents.append({
                    "type": "input_audio",
                    "input_audio": {"data": data, "format": audio_format},
                })
            elif item.media_type == "application/pdf":
                filename = str(
                    item.additional_properties.get("filename") or "attachment.pdf"
                )
                contents.append({
                    "type": "input_file",
                    "filename": filename,
                    "file_data": item.uri,
                })
        if contents:
            result.append({"role": message.role, "content": contents})
    return result


def _anthropic_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        role = "assistant" if message.role == "assistant" else "user"
        content: list[dict[str, Any]] = []
        for item in message.contents:
            if item.type == "text":
                content.append({"type": "text", "text": item.text})
                continue
            if item.type != "data" or not item.uri or not item.media_type:
                continue
            if not item.uri.startswith("data:") or ";base64," not in item.uri:
                raise ValueError("Chat attachments must use base64 data URIs")
            encoded = item.uri.split(";base64,", 1)[1]
            try:
                base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Chat attachment contains invalid base64 data") from exc
            if item.media_type.startswith("image/") and role == "user":
                if item.media_type not in {
                    "image/jpeg", "image/png", "image/gif", "image/webp"
                }:
                    raise ValueError(
                        f"Microsoft Foundry Anthropic chat does not support "
                        f"image type {item.media_type}"
                    )
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.media_type,
                        "data": encoded,
                    },
                })
            elif item.media_type == "application/pdf" and role == "user":
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": encoded,
                    },
                })
            elif item.media_type.startswith("audio/"):
                raise ValueError(
                    "Microsoft Foundry Anthropic chat does not support audio "
                    "attachments. Choose a Foundry Responses model for audio."
                )
        if not content:
            continue
        if result and result[-1]["role"] == role:
            result[-1]["content"].extend(content)
        else:
            result.append({"role": role, "content": content})
    return result


def _response_attachments(response: Any) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []

    def collect(item: Any, depth: int = 0) -> None:
        if depth > 4:
            return
        uri = getattr(item, "uri", None)
        if getattr(item, "type", None) in {"data", "uri"} and isinstance(uri, str):
            if uri.startswith("data:") and ";base64," in uri:
                metadata, encoded = uri.split(",", 1)
                media_type = metadata[5:].split(";", 1)[0] or item.media_type
                try:
                    base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    return
                if media_type:
                    filename = getattr(item, "additional_properties", {}).get(
                        "filename"
                    )
                    extension = {
                        "image/png": ".png",
                        "image/jpeg": ".jpg",
                        "image/webp": ".webp",
                        "application/pdf": ".pdf",
                    }.get(media_type, "")
                    attachments.append({
                        "name": filename or f"generated-{len(attachments) + 1}{extension}",
                        "media_type": media_type,
                        "data": encoded,
                    })
            return
        for field in ("outputs", "items"):
            children = getattr(item, field, None)
            if isinstance(children, (list, tuple)):
                for child in children:
                    collect(child, depth + 1)

    for message in getattr(response, "messages", []):
        if getattr(message, "role", None) in {"assistant", "tool"}:
            for item in getattr(message, "contents", []):
                collect(item)
    return attachments


def _generated_file_blocks(text: str) -> list[dict[str, str]]:
    files = []
    for name, contents in re.findall(
        r"```file\s+([^\r\n]+)\r?\n(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        filename = name.strip().replace("\\", "/").rsplit("/", 1)[-1]
        data = contents.encode("utf-8")
        if not filename or len(data) > 10 * 1024 * 1024:
            continue
        files.append({
            "name": filename[:255],
            "media_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "data": base64.b64encode(data).decode("ascii"),
        })
    return files


async def generate_chat_response(
    messages: Sequence[Message],
    instructions: str,
    model: str,
    provider: str | None = None,
    enable_native_tools: bool = True,
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    on_usage: Callable[[ChatUsage], None] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    settings = get_settings()
    selected_provider = (provider or settings.model_provider).casefold()
    if selected_provider == "foundry-anthropic":
        if not settings.foundry_anthropic_endpoint:
            raise RuntimeError(
                "Microsoft Foundry Anthropic is configured but "
                "WORKBENCH_FOUNDRY_ANTHROPIC_ENDPOINT is unset"
            )
        selected_model = (
            settings.foundry_anthropic_model
            if model in {"", "auto"}
            else model
        )
        response = await FoundryAnthropicProvider(
            endpoint=settings.foundry_anthropic_endpoint,
            model=selected_model,
        ).run(
            instructions=instructions,
            messages=_anthropic_messages(messages),
            on_text_delta=on_text_delta,
        )
        usage = response.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        if on_usage:
            on_usage(ChatUsage(
                provider=selected_provider,
                model=str(response.get("model") or selected_model),
                input_tokens=_token_count(usage.get("input_tokens")),
                output_tokens=_token_count(usage.get("output_tokens")),
                cache_read_tokens=_token_count(
                    usage.get("cache_read_input_tokens")
                ) or 0,
                cache_write_tokens=_token_count(
                    usage.get("cache_creation_input_tokens")
                ) or 0,
            ))
        content = response.get("content")
        text = "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ) if isinstance(content, list) else ""
        return text, _generated_file_blocks(text)
    if selected_provider == "foundry":
        if not settings.foundry_responses_endpoint:
            raise RuntimeError(
                "Microsoft Foundry is configured but "
                "WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
            )
        selected_model = (
            settings.foundry_model if model in {"", "auto"} else model
        )
        image_generation_deployment = (
            settings.foundry_image_generation_deployment
        )
        tool_schemas = [{"type": "web_search"}] if enable_native_tools else []
        if enable_native_tools and image_generation_deployment:
            tool_schemas.append({"type": "image_generation"})
        response_payloads: list[dict[str, Any]] = []

        def capture_response(payload: dict[str, Any]) -> None:
            response_payloads.append(payload)

        text = await FoundryResponsesProvider(
            endpoint=settings.foundry_responses_endpoint,
            model=selected_model,
            reasoning_summary=settings.foundry_reasoning_summary,
            tool_schemas=tool_schemas,
            image_generation_deployment=image_generation_deployment,
        ).run(
            instructions=instructions,
            prompt="",
            runtime=_NoToolsRuntime(),
            callback=_ignore_event,
            max_steps=1,
            verbose_logging=False,
            input_messages=_foundry_messages(messages),
            on_response=capture_response,
            on_text_delta=on_text_delta,
        )
        if on_usage:
            response = response_payloads[-1] if response_payloads else {}
            token_usage = response.get("usage")
            token_usage = token_usage if isinstance(token_usage, dict) else {}
            input_details = token_usage.get("input_tokens_details")
            input_details = input_details if isinstance(input_details, dict) else {}
            on_usage(ChatUsage(
                provider=selected_provider,
                model=str(response.get("model") or selected_model),
                input_tokens=_token_count(token_usage.get("input_tokens")),
                output_tokens=_token_count(token_usage.get("output_tokens")),
                cache_read_tokens=_token_count(
                    input_details.get("cached_tokens")
                ) or 0,
            ))
        return (
            text,
            _foundry_response_attachments(response_payloads)
            + _generated_file_blocks(text),
        )

    if selected_provider == "ollama":
        agent = OllamaChatClient(host=settings.ollama_url, model=model).as_agent(
            instructions=instructions, default_options={"model": model}
        )
    elif selected_provider == "copilot":
        options: dict[str, Any] = {
            "cli_path": settings.copilot_cli_path,
            "timeout": float(settings.model_request_timeout_seconds),
            "base_directory": str(Path(settings.copilot_home).expanduser().resolve()),
            "enable_file_hooks": False,
            "available_tools": [],
        }
        if model not in {"", "auto"}:
            options["model"] = model
        agent = GitHubCopilotAgent(
            instructions=instructions, default_options=options)
    else:
        raise RuntimeError(f"Unsupported model provider: {selected_provider}")
    async with agent:
        if on_text_delta:
            response_stream = agent.run(messages, stream=True)
            async for update in response_stream:
                if update.text:
                    await on_text_delta(update.text)
            response = await response_stream.get_final_response()
        else:
            response = await agent.run(messages)
    if on_usage:
        usage_details = getattr(response, "usage_details", None)
        usage_details = usage_details if isinstance(usage_details, dict) else {}
        additional_properties = getattr(response, "additional_properties", None)
        additional_properties = (
            additional_properties
            if isinstance(additional_properties, dict)
            else {}
        )
        on_usage(ChatUsage(
            provider=selected_provider,
            model=str(additional_properties.get("model") or model),
            input_tokens=_token_count(
                usage_details.get("input_token_count")
            ),
            output_tokens=_token_count(
                usage_details.get("output_token_count")
            ),
            cache_read_tokens=_token_count(
                usage_details.get("cache_read_input_token_count")
            ) or 0,
            cache_write_tokens=_token_count(
                usage_details.get("cache_creation_input_token_count")
            ) or 0,
        ))
    return (
        response.text,
        _response_attachments(response) + _generated_file_blocks(response.text),
    )


def _foundry_response_attachments(
    responses: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    for response in responses:
        for item in response.get("output", []):
            if not isinstance(item, dict):
                continue
            data = item.get("result")
            if (
                item.get("type") == "image_generation_call"
                and isinstance(data, str)
                and data
            ):
                if data.startswith("data:") and ";base64," in data:
                    metadata, data = data.split(",", 1)
                    media_type = metadata[5:].split(";", 1)[0] or "image/png"
                else:
                    media_type = "image/png"
                try:
                    base64.b64decode(data, validate=True)
                except (binascii.Error, ValueError):
                    data = ""
                if data:
                    extension = ".jpg" if media_type == "image/jpeg" else ".png"
                    attachments.append({
                        "name": f"generated-image-{len(attachments) + 1}{extension}",
                        "media_type": media_type,
                        "data": data,
                    })
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                uri = content.get("image_url") or content.get("url")
                if (
                    content.get("type") == "output_image"
                    and isinstance(uri, str)
                    and uri.startswith("data:")
                    and ";base64," in uri
                ):
                    metadata, encoded = uri.split(",", 1)
                    media_type = metadata[5:].split(";", 1)[0] or "image/png"
                    try:
                        base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError):
                        continue
                    attachments.append({
                        "name": f"generated-image-{len(attachments) + 1}.png",
                        "media_type": media_type,
                        "data": encoded,
                    })
    return attachments


class _NoToolsRuntime:
    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"Text generation requested unavailable tool: {name}")


async def _ignore_event(
    event_type: str,
    title: str,
    detail: str,
    severity: str,
    data: dict[str, Any] | None,
) -> None:
    return None


async def generate_text(
    model: str, instructions: str, prompt: str, provider: str | None = None
) -> str:
    settings = get_settings()
    selected_provider = (provider or settings.model_provider).casefold()
    if selected_provider == "foundry-anthropic":
        if not settings.foundry_anthropic_endpoint:
            raise RuntimeError(
                "Microsoft Foundry Anthropic is configured but "
                "WORKBENCH_FOUNDRY_ANTHROPIC_ENDPOINT is unset"
            )
        selected_model = (
            settings.foundry_anthropic_model
            if model in {"", "auto"}
            else model
        )
        response = await FoundryAnthropicProvider(
            endpoint=settings.foundry_anthropic_endpoint,
            model=selected_model,
        ).run(
            instructions=instructions,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.get("content")
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ) if isinstance(content, list) else ""
    if selected_provider == "foundry":
        if not settings.foundry_responses_endpoint:
            raise RuntimeError(
                "Microsoft Foundry is configured but "
                "WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
            )
        selected_model = (
            settings.foundry_model if model in {"", "auto"} else model
        )
        return await FoundryResponsesProvider(
            endpoint=settings.foundry_responses_endpoint,
            model=selected_model,
            reasoning_summary=settings.foundry_reasoning_summary,
        ).run(
            instructions=instructions,
            prompt=prompt,
            runtime=_NoToolsRuntime(),
            callback=_ignore_event,
            max_steps=1,
            verbose_logging=False,
        )
    if selected_provider == "ollama":
        agent = OllamaChatClient(host=settings.ollama_url, model=model).as_agent(
            instructions=instructions, default_options={"model": model}
        )
    elif selected_provider == "copilot":
        options: dict[str, Any] = {
            "cli_path": settings.copilot_cli_path,
            "timeout": float(settings.model_request_timeout_seconds),
            "base_directory": str(Path(settings.copilot_home).expanduser().resolve()),
            "enable_file_hooks": False,
            "available_tools": [],
        }
        if model not in {"", "auto"}:
            options["model"] = model
        agent = GitHubCopilotAgent(
            instructions=instructions, default_options=options)
    else:
        raise RuntimeError(f"Unsupported model provider: {selected_provider}")
    async with agent:
        response = await agent.run(prompt)
    return response.text
