from typing import Any

from ..config import get_settings
from .copilot import copilot_models


def usd_rate_card(model: dict[str, Any]) -> dict[str, Any] | None:
    billing = model.get("billing")
    prices = billing.get("token_prices") if isinstance(billing, dict) else None
    if not isinstance(prices, dict) or not prices.get("batch_size"):
        return None
    batch_size = float(prices["batch_size"])
    usd_per_credit = 0.01
    per_million = 1_000_000 / batch_size

    def tier(source: dict[str, Any]) -> dict[str, float]:
        return {
            key: float(source.get(field) or 0) * usd_per_credit * per_million
            for key, field in {
                "input_per_million_usd": "input_price",
                "output_per_million_usd": "output_price",
                "cache_read_per_million_usd": "cache_read_price",
                "cache_write_per_million_usd": "cache_write_price",
            }.items()
        }

    rate: dict[str, Any] = {
        **tier(prices),
        "source": "GitHub Copilot CLI AI Credits (1 credit = $0.01 USD)",
    }
    discount = float(billing.get("discount_percent") or 0)
    if discount:
        rate["discount_percent"] = discount
    long_context = prices.get("long_context")
    if isinstance(long_context, dict):
        rate["long_context"] = {
            **tier(long_context),
            "threshold_input_tokens": int(
                prices.get("max_prompt_tokens") or prices.get(
                    "context_max") or 0
            ),
        }
    return rate


async def runtime_model_pricing() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    if settings.model_provider.casefold() != "copilot":
        return {}
    try:
        models = await copilot_models()
    except RuntimeError:
        return {}
    return {
        f"copilot/{model['name']}": rate
        for model in models
        if model.get("name") and (rate := usd_rate_card(model)) is not None
    }
