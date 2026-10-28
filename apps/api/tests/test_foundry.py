import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent_framework import Content, Message
import httpx
import pytest

from app.foundry import FoundryApiError, FoundryContentFilterError, FoundryResponsesProvider
from app.model_catalog.catalog import list_runtime_models
from app.model_catalog.generation import (
    ChatUsage,
    _foundry_messages,
    generate_chat_response,
)
from app.foundry.parsing import foundry_error
from app.telemetry import estimate_model_call_cost


class RecordingRuntime:
    def __init__(self):
        self.calls = []

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": "package"}


def test_foundry_api_error_preserves_validation_detail():
    error = foundry_error(400, {
        "error": {
            "code": "invalid_request_error",
            "param": "tools[0].type",
            "message": "Unsupported tool type",
        },
    })

    assert isinstance(error, FoundryApiError)
    assert error.status_code == 400
    assert error.code == "invalid_request_error"
    assert str(error) == (
        "Microsoft Foundry request failed with HTTP 400 "
        "(invalid_request_error, parameter tools[0].type): Unsupported tool type"
    )


def test_foundry_chat_history_uses_output_text_for_assistant_messages():
    messages = _foundry_messages([
        Message("user", [Content.from_text("First question")]),
        Message("assistant", [Content.from_text("First answer")]),
        Message("user", [Content.from_text("Follow-up")]),
    ])

    assert [message["content"][0]["type"] for message in messages] == [
        "input_text",
        "output_text",
        "input_text",
    ]


@pytest.mark.asyncio
async def test_runtime_model_catalog_lists_comma_separated_foundry_models():
    with patch(
        "app.model_catalog.catalog.get_settings",
        return_value=SimpleNamespace(
            model_provider="foundry",
            foundry_responses_endpoint="https://foundry.example/responses",
            foundry_model="gpt-6-sol",
            foundry_models="gpt-6.1-sol, gpt-6-sol, gpt-6.2-sol",
        ),
    ):
        models = await list_runtime_models()

    assert [model["name"] for model in models] == [
        "gpt-6-sol",
        "gpt-6.1-sol",
        "gpt-6.2-sol",
    ]
    assert all(model["provider"] == "foundry" for model in models)


def test_model_call_cost_uses_configured_provider_and_model_rates():
    with patch(
        "app.telemetry.get_settings",
        return_value=SimpleNamespace(
            model_pricing_json=(
                '{"foundry/gpt-6-sol": {'
                '"input_per_million_usd": 2, '
                '"output_per_million_usd": 10}}'
            )
        ),
    ):
        cost, note = estimate_model_call_cost(
            "foundry", "gpt-6-sol", 1000, 100
        )

    assert cost == 0.003
    assert note == "Configured rate card estimate"


def test_foundry_image_generation_requires_a_deployment():
    with pytest.raises(
        RuntimeError,
        match="WORKBENCH_FOUNDRY_IMAGE_GENERATION_DEPLOYMENT",
    ):
        FoundryResponsesProvider(
            endpoint="https://foundry.example/openai/v1/responses",
            model="test-model",
            tool_schemas=[{"type": "image_generation"}],
        )


@pytest.mark.asyncio
async def test_foundry_sends_image_generation_deployment_header():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.headers["x-ms-oai-image-generation-deployment"]
            == "image-deployment"
        )
        return httpx.Response(200, json={"id": "response-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        tool_schemas=[{"type": "image_generation"}],
        image_generation_deployment="image-deployment",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )

    result = await provider._request({"model": "test-model"})

    assert result == {"id": "response-1"}
    await client.aclose()


@pytest.mark.asyncio
async def test_foundry_web_search_is_auto_selected_and_citations_are_preserved():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "response-search",
            "model": "test-model",
            "output_text": "The latest update is available [here](https://example.test/update).",
            "output": [{
                "type": "web_search_call",
                "id": "search-1",
                "status": "completed",
            }],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        tool_schemas=[{"type": "web_search"}],
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )

    async def callback(*_args):
        return None

    result = await provider.run(
        instructions="Use web search for current facts.",
        prompt="What changed recently?",
        runtime=RecordingRuntime(),
        callback=callback,
        max_steps=1,
        verbose_logging=False,
    )

    assert requests[0]["tools"] == [{"type": "web_search"}]
    assert requests[0]["tool_choice"] == "auto"
    assert result == (
        "The latest update is available [here](https://example.test/update)."
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_foundry_streams_text_deltas_and_returns_completed_response():
    events = [
        {"type": "response.output_text.delta", "delta": "Hello"},
        {"type": "response.output_text.delta", "delta": " from Foundry."},
        {
            "type": "response.completed",
            "response": {
                "id": "response-stream",
                "model": "test-model",
                "output_text": "Hello from Foundry.",
            },
        },
    ]
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
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
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    chunks = []

    async def on_text_delta(text: str) -> None:
        chunks.append(text)

    async def callback(*_args):
        return None

    result = await provider.run(
        instructions="Answer briefly.",
        prompt="Say hello.",
        runtime=RecordingRuntime(),
        callback=callback,
        max_steps=1,
        verbose_logging=False,
        on_text_delta=on_text_delta,
    )

    assert requests[0]["stream"] is True
    assert chunks == ["Hello", " from Foundry."]
    assert result == "Hello from Foundry."
    await client.aclose()


@pytest.mark.asyncio
async def test_foundry_continues_response_with_governed_tool_result():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json={
                "id": "response-1",
                "model": "test-model",
                "output": [{
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "read_file",
                    "arguments": '{"path":"package.json"}',
                }],
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            })
        return httpx.Response(200, json={
            "id": "response-2",
            "model": "test-model",
            "output_text": "Implemented and validated.",
            "usage": {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        reasoning_summary="auto",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    runtime = RecordingRuntime()
    events = []

    async def callback(event_type, title, detail, severity, data):
        events.append((event_type, title, detail, severity, data))

    result = await provider.run(
        instructions="Use governed tools.",
        prompt="Inspect package.json",
        runtime=runtime,
        callback=callback,
        max_steps=4,
        verbose_logging=False,
    )

    assert result == "Implemented and validated."
    assert runtime.calls == [("read_file", {"path": "package.json"})]
    assert requests[1]["previous_response_id"] == "response-1"
    assert requests[1]["input"] == [{
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"content": "package"}',
    }]
    assert requests[0]["reasoning"] == {"summary": "auto"}
    assert [event[0] for event in events].count("model.completed") == 2
    assert events[-1][0] == "agent.message"
    await client.aclose()


@pytest.mark.asyncio
async def test_foundry_reports_sanitized_content_filter_metadata():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={
            "error": {
                "message": "sensitive provider detail",
                "code": "content_filter",
                "innererror": {"code": "ContentFiltered"},
                "content_filters": [{
                    "blocked": True,
                    "source_type": "prompt",
                    "content_filter_results": {
                        "jailbreak": {"detected": True, "filtered": True},
                        "hate": {"filtered": False},
                    },
                }],
            },
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    events = []

    async def callback(event_type, title, detail, severity, data):
        events.append((event_type, title, detail, severity, data))

    with pytest.raises(FoundryContentFilterError) as captured:
        await provider.run(
            instructions="Use governed tools.",
            prompt="Run the canary",
            runtime=RecordingRuntime(),
            callback=callback,
            max_steps=1,
            verbose_logging=False,
        )

    assert captured.value.categories == ["jailbreak"]
    guardrail = events[-1]
    assert guardrail[0] == "model.guardrail_triggered"
    assert guardrail[4]["guardrail_categories"] == ["jailbreak"]
    assert "sensitive provider detail" not in json.dumps(events)
    await client.aclose()


@pytest.mark.asyncio
async def test_foundry_accepts_multimodal_chat_history_and_captures_output():
    requests = []
    responses = []
    generated = "aGVsbG8="

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "response-media",
            "model": "test-model",
            "output_text": "Here is the generated result.",
            "output": [{
                "type": "image_generation_call",
                "result": generated,
            }],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    result = await provider.run(
        instructions="Answer the user.",
        prompt="",
        runtime=RecordingRuntime(),
        callback=AsyncMock(),
        max_steps=1,
        verbose_logging=False,
        input_messages=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe and draw this"},
                {"type": "input_image", "image_url": "data:image/png;base64,aGVsbG8="},
            ],
        }],
        on_response=responses.append,
    )

    assert result == "Here is the generated result."
    assert requests[0]["input"][0]["content"][1]["type"] == "input_image"
    assert responses[0]["output"][0]["result"] == generated
    await client.aclose()


@pytest.mark.asyncio
async def test_chat_generation_routes_media_and_image_outputs_through_foundry():
    image = base64.b64encode(b"generated image").decode("ascii")
    response = {
        "model": "selected-model",
        "usage": {
            "input_tokens": 11,
            "output_tokens": 4,
            "input_tokens_details": {"cached_tokens": 2},
        },
        "output": [{
            "type": "image_generation_call",
            "result": image,
        }],
    }

    async def run(**kwargs):
        kwargs["on_response"](response)
        return "Here is the image.\n\n```file notes.txt\nHello\n```"

    fake_provider = SimpleNamespace(run=AsyncMock(side_effect=run))
    usage = []
    with patch(
        "app.model_catalog.generation.get_settings",
        return_value=SimpleNamespace(
            model_provider="foundry",
            foundry_responses_endpoint="https://foundry.example/responses",
            foundry_model="foundry-default",
            foundry_reasoning_summary=None,
            foundry_image_generation_deployment="image-deployment",
        ),
    ), patch(
        "app.model_catalog.generation.FoundryResponsesProvider",
        return_value=fake_provider,
    ) as provider_factory:
        text, attachments = await generate_chat_response(
            messages=[Message("user", [
                Content.from_text("Draw this"),
                Content.from_data(b"source image", "image/png"),
                Content.from_data(b"voice input", "audio/wav"),
            ])],
            instructions="You are a helpful assistant.",
            model="selected-model",
            provider="foundry",
            on_usage=usage.append,
        )

    assert text.startswith("Here is the image.")
    provider_factory.assert_called_once()
    assert provider_factory.call_args.kwargs["tool_schemas"] == [
        {"type": "web_search"},
        {"type": "image_generation"},
    ]
    assert (
        provider_factory.call_args.kwargs["image_generation_deployment"]
        == "image-deployment"
    )
    sent_messages = fake_provider.run.await_args.kwargs["input_messages"]
    assert sent_messages[0]["content"][1]["type"] == "input_image"
    assert sent_messages[0]["content"][2] == {
        "type": "input_audio",
        "input_audio": {
            "data": base64.b64encode(b"voice input").decode("ascii"),
            "format": "wav",
        },
    }
    assert [item["name"] for item in attachments] == [
        "generated-image-1.png",
        "notes.txt",
    ]
    assert usage == [ChatUsage(
        provider="foundry",
        model="selected-model",
        input_tokens=11,
        output_tokens=4,
        cache_read_tokens=2,
    )]


@pytest.mark.asyncio
async def test_foundry_chat_omits_image_tool_without_deployment():
    fake_provider = SimpleNamespace(run=AsyncMock(return_value="Hello."))
    with patch(
        "app.model_catalog.generation.get_settings",
        return_value=SimpleNamespace(
            model_provider="foundry",
            foundry_responses_endpoint="https://foundry.example/responses",
            foundry_model="foundry-default",
            foundry_reasoning_summary=None,
            foundry_image_generation_deployment=None,
        ),
    ), patch(
        "app.model_catalog.generation.FoundryResponsesProvider",
        return_value=fake_provider,
    ) as provider_factory:
        text, attachments = await generate_chat_response(
            messages=[Message("user", [Content.from_text("Hello")])],
            instructions="You are a helpful assistant.",
            model="auto",
            provider="foundry",
        )

    assert text == "Hello."
    assert attachments == []
    assert provider_factory.call_args.kwargs["tool_schemas"] == [
        {"type": "web_search"},
    ]
    assert provider_factory.call_args.kwargs["image_generation_deployment"] is None


@pytest.mark.asyncio
async def test_copilot_chat_returns_generated_images_when_provider_supplies_them():
    captured = {}

    class FakeAgent:
        def __init__(self, *, instructions, default_options):
            captured["instructions"] = instructions
            captured["default_options"] = default_options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def run(self, _messages):
            return SimpleNamespace(
                text="Generated an image.",
                messages=[Message(
                    "assistant",
                    [Content.from_data(b"generated image", "image/png")],
                )],
            )

    settings = SimpleNamespace(
        copilot_cli_path="copilot",
        model_request_timeout_seconds=60,
        copilot_home="~/.copilot",
    )
    with patch(
        "app.model_catalog.generation.get_settings", return_value=settings
    ), patch(
        "app.model_catalog.generation.GitHubCopilotAgent", FakeAgent
    ):
        text, attachments = await generate_chat_response(
            messages=[Message("user", [Content.from_text("Draw a cat.")])],
            instructions="You are a helpful assistant.",
            model="selected-model",
            provider="copilot",
        )

    assert "image_generation" not in captured["default_options"]
    assert text == "Generated an image."
    assert attachments == [{
        "name": "generated-1.png",
        "media_type": "image/png",
        "data": base64.b64encode(b"generated image").decode("ascii"),
    }]


@pytest.mark.asyncio
async def test_copilot_chat_streams_agent_framework_text_updates():
    class FakeStream:
        def __aiter__(self):
            async def updates():
                yield SimpleNamespace(text="Streaming ")
                yield SimpleNamespace(text="response.")

            return updates()

        async def get_final_response(self):
            return SimpleNamespace(
                text="Streaming response.",
                messages=[Message(
                    "assistant", [Content.from_text("Streaming response.")]
                )],
            )

    class FakeAgent:
        def __init__(self, *, instructions, default_options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def run(self, _messages, *, stream=False):
            assert stream
            return FakeStream()

    settings = SimpleNamespace(
        copilot_cli_path="copilot",
        model_request_timeout_seconds=60,
        copilot_home="~/.copilot",
    )
    chunks = []

    async def on_text_delta(text: str) -> None:
        chunks.append(text)

    with patch(
        "app.model_catalog.generation.get_settings", return_value=settings
    ), patch(
        "app.model_catalog.generation.GitHubCopilotAgent", FakeAgent
    ):
        text, _attachments = await generate_chat_response(
            messages=[Message("user", [Content.from_text("Say hello.")])],
            instructions="Answer briefly.",
            model="selected-model",
            provider="copilot",
            on_text_delta=on_text_delta,
        )

    assert chunks == ["Streaming ", "response."]
    assert text == "Streaming response."


@pytest.mark.asyncio
async def test_foundry_guardrail_probe_returns_only_sanitized_filter_evidence():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={
            "error": {
                "message": "provider detail must not escape",
                "code": "content_filter",
                "innererror": {"code": "ContentFiltered"},
                "content_filters": [{
                    "blocked": True,
                    "source_type": "prompt",
                    "content_filter_results": {
                        "jailbreak": {"detected": True, "filtered": True},
                    },
                }],
            },
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoundryResponsesProvider(
        endpoint="https://foundry.example/openai/v1/responses",
        model="test-model",
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )

    result = await provider.probe_content_filter()

    assert result == {
        "passed": True,
        "blocked": True,
        "status_code": 400,
        "error_code": "content_filter",
        "guardrail_categories": ["jailbreak"],
        "content_source": "prompt",
    }
    assert requests[0]["max_output_tokens"] == 16
    assert "provider detail" not in json.dumps(result)
    assert "credentials" not in json.dumps(result)
    await client.aclose()
