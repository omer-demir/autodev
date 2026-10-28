import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agent_framework import Content, Message
from fastapi.testclient import TestClient
import httpx
import pytest

from app.foundry.anthropic_provider import FoundryAnthropicProvider
from app.main import app
from app.model_catalog.catalog import list_runtime_models
from app.model_catalog.generation import (
    ChatUsage,
    _anthropic_messages,
    generate_chat_response,
)


@pytest.mark.asyncio
async def test_anthropic_provider_posts_to_messages_api_with_entra_token():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "id": "msg_1",
            "model": "claude-deployment",
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 2},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryAnthropicProvider(
        endpoint="https://foundry.example/anthropic",
        model="claude-deployment",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )

    result = await provider.run(
        instructions="Be helpful.",
        messages=[{"role": "user", "content": "Hello"}],
    )

    request = requests[0]
    assert str(request.url) == (
        "https://foundry.example/anthropic/v1/messages"
    )
    assert request.headers["authorization"] == "Bearer test-token"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert json.loads(request.content) == {
        "model": "claude-deployment",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": "Hello"}],
        "system": "Be helpful.",
        "stream": False,
    }
    assert result["content"][0]["text"] == "Hello"
    await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_provider_streams_text_and_usage():
    async def handler(_request: httpx.Request) -> httpx.Response:
        events = [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stream",
                    "model": "claude-deployment",
                    "usage": {"input_tokens": 11},
                },
            },
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Hello"},
            },
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": " streamed"},
            },
            {
                "type": "message_delta",
                "usage": {"output_tokens": 3},
            },
        ]
        body = "".join(
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            for event in events
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryAnthropicProvider(
        endpoint="https://foundry.example/anthropic/v1/messages",
        model="claude-deployment",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    deltas = []

    async def on_delta(text: str) -> None:
        deltas.append(text)

    result = await provider.run(
        instructions="",
        messages=[{"role": "user", "content": "Hello"}],
        on_text_delta=on_delta,
    )

    assert deltas == ["Hello", " streamed"]
    assert result["content"] == [{
        "type": "text",
        "text": "Hello streamed",
    }]
    assert result["usage"]["input_tokens"] == 11
    assert result["usage"]["output_tokens"] == 3
    await client.aclose()


def test_anthropic_messages_convert_text_images_and_pdf():
    messages = _anthropic_messages([
        Message("user", [
            Content.from_text("Inspect these."),
            Content.from_data(b"image-bytes", "image/png"),
            Content.from_data(
                b"pdf-bytes",
                "application/pdf",
                additional_properties={"filename": "report.pdf"},
            ),
        ]),
        Message("assistant", [Content.from_text("I will inspect them.")]),
        Message("user", [Content.from_text("Thanks.")]),
    ])

    assert [message["role"] for message in messages] == [
        "user", "assistant", "user",
    ]
    assert messages[0]["content"][0] == {
        "type": "text",
        "text": "Inspect these.",
    }
    assert messages[0]["content"][1]["type"] == "image"
    assert messages[0]["content"][1]["source"]["media_type"] == "image/png"
    assert messages[0]["content"][2] == {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": "cGRmLWJ5dGVz",
        },
    }


@pytest.mark.asyncio
async def test_anthropic_chat_generation_reports_model_and_cached_usage():
    async def run(*, instructions, messages, on_text_delta=None):
        assert instructions == "Be concise."
        assert messages == [{"role": "user", "content": [
            {"type": "text", "text": "Hi"},
        ]}]
        assert on_text_delta is None
        return {
            "model": "claude-deployment",
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "cache_read_input_tokens": 4,
                "cache_creation_input_tokens": 1,
            },
        }

    usage = []
    with patch(
        "app.model_catalog.generation.get_settings",
        return_value=SimpleNamespace(
            foundry_anthropic_endpoint="https://foundry.example/anthropic",
            foundry_anthropic_model="claude-default",
        ),
    ), patch(
        "app.model_catalog.generation.FoundryAnthropicProvider"
    ) as provider_class:
        provider_class.return_value.run = AsyncMock(side_effect=run)
        text, attachments = await generate_chat_response(
            messages=[Message("user", [Content.from_text("Hi")])],
            instructions="Be concise.",
            model="claude-deployment",
            provider="foundry-anthropic",
            on_usage=usage.append,
        )

    assert text == "Hello"
    assert attachments == []
    assert usage == [ChatUsage(
        provider="foundry-anthropic",
        model="claude-deployment",
        input_tokens=10,
        output_tokens=2,
        cache_read_tokens=4,
        cache_write_tokens=1,
    )]


@pytest.mark.asyncio
async def test_foundry_model_catalog_lists_responses_and_anthropic_deployments():
    settings = SimpleNamespace(
        model_provider="foundry",
        foundry_responses_endpoint="https://foundry.example/openai/v1/responses",
        foundry_model="gpt-default",
        foundry_models="gpt-extra",
        foundry_anthropic_endpoint="https://foundry.example/anthropic",
        foundry_anthropic_model="claude-default",
        foundry_anthropic_models="claude-extra",
    )
    with patch("app.model_catalog.catalog.get_settings", return_value=settings):
        models = await list_runtime_models()

    assert [(item["provider"], item["name"]) for item in models] == [
        ("foundry", "gpt-default"),
        ("foundry", "gpt-extra"),
        ("foundry-anthropic", "claude-default"),
        ("foundry-anthropic", "claude-extra"),
    ]
    settings.model_provider = "foundry-anthropic"
    with patch("app.model_catalog.catalog.get_settings", return_value=settings):
        models = await list_runtime_models()
    assert [item["provider"] for item in models] == [
        "foundry-anthropic",
        "foundry-anthropic",
        "foundry",
        "foundry",
    ]


def test_repository_free_chat_can_switch_provider_for_each_turn():
    answers = iter(["Foundry answer.", "Anthropic answer."])

    async def generate_response(*, model, provider, on_usage, **_kwargs):
        on_usage(SimpleNamespace(
            provider=provider,
            model=model,
            input_tokens=8,
            output_tokens=3,
            cache_read_tokens=0,
            cache_write_tokens=0,
        ))
        return next(answers), []

    with TestClient(app) as client, patch(
        "app.main.list_runtime_models",
        new=AsyncMock(return_value=[{
            "name": "gpt-deployment",
            "provider": "foundry",
        }]),
    ), patch(
        "app.main.list_provider_models",
        new=AsyncMock(return_value=[{
            "name": "claude-deployment",
            "provider": "foundry-anthropic",
        }]),
    ), patch(
        "app.main.generate_chat_response",
        new=AsyncMock(side_effect=generate_response),
    ):
        created = client.post("/api/chats", json={
            "message": f"Start chat {uuid4().hex}",
            "model_name": "gpt-deployment",
            "model_provider": "foundry",
        })
        assert created.status_code == 202, created.text
        chat_id = created.json()["chat"]["id"]
        assert created.json()["chat"]["model_provider"] == "foundry"

        follow_up = client.post(
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Switch to Claude.",
                "model_name": "claude-deployment",
                "model_provider": "foundry-anthropic",
            },
        )
        assert follow_up.status_code == 202, follow_up.text
        result = follow_up.json()
        assert result["chat"]["model_provider"] == "foundry-anthropic"
        assert result["chat"]["model_name"] == "claude-deployment"
        assert result["messages"][-1]["model_provider"] == "foundry-anthropic"
        assert result["messages"][-1]["model_name"] == "claude-deployment"
