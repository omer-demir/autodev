import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.foundry import FoundryContentFilterError, FoundryResponsesProvider


class RecordingRuntime:
    def __init__(self):
        self.calls = []

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": "package"}


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
