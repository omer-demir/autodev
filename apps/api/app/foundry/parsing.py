from typing import Any

from .api_error import FoundryApiError
from .content_filter_error import FoundryContentFilterError


def foundry_error(status_code: int, payload: Any) -> FoundryApiError:
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    code = str(error.get("code") or "provider_error")
    if code == "content_filter" or error.get("innererror", {}).get("code") == "ContentFiltered":
        categories: set[str] = set()
        source = "unknown"
        for item in error.get("content_filters", []):
            if not isinstance(item, dict) or not item.get("blocked"):
                continue
            source = str(item.get("source_type") or source)
            for category, result in item.get("content_filter_results", {}).items():
                if isinstance(result, dict) and (
                    result.get("filtered") or result.get("detected")
                ):
                    categories.add(str(category))
        return FoundryContentFilterError(
            status_code,
            code=code,
            inner_code=error.get("innererror", {}).get("code"),
            categories=sorted(categories),
            source=source,
        )
    return FoundryApiError(
        status_code,
        code,
        f"Microsoft Foundry request failed with HTTP {status_code}",
    )


def function_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    return [
        item
        for item in output
        if isinstance(item, dict)
        and item.get("type") == "function_call"
        and item.get("call_id")
        and item.get("name")
    ]


def response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                parts.append(str(content.get("text") or ""))
    return "".join(parts).strip()


def reasoning_summary(payload: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        for summary in item.get("summary", []):
            if isinstance(summary, dict) and summary.get("text"):
                parts.append(str(summary["text"]))
    value = "\n".join(parts).strip()
    return value or None


def usage(payload: dict[str, Any]) -> dict[str, int]:
    usage_data = payload.get("usage") if isinstance(
        payload.get("usage"), dict) else {}
    return {
        "input_tokens": int(usage_data.get("input_tokens") or 0),
        "output_tokens": int(usage_data.get("output_tokens") or 0),
        "total_tokens": int(usage_data.get("total_tokens") or 0),
        "cache_read_tokens": int(
            (usage_data.get("input_tokens_details") or {}).get("cached_tokens") or 0
        ),
        "reasoning_tokens": int(
            (usage_data.get("output_tokens_details")
             or {}).get("reasoning_tokens") or 0
        ),
    }
