from typing import Any

from .specs import generate_adapter_specs, validate_adapter_specs


def adapter_bundle(
    dataset: dict[str, Any], agent: dict[str, Any]
) -> dict[str, Any]:
    scenarios = dataset.get("scenarios")
    if not isinstance(scenarios, list):
        raise TypeError(
            "Evaluation dataset payload requires a scenarios list; "
            "the full dataset record must be passed to an adapter"
        )
    bundle = dataset.get("adapter_specs") or {}
    if not bundle:
        if dataset.get("status") == "FROZEN":
            raise ValueError(
                "Frozen dataset is missing canonical adapter specs"
            )
        bundle = generate_adapter_specs(
            scenarios,
            agent,
            str(dataset.get("agent_version", "legacy")),
            str(dataset.get("suite_version", "legacy")),
        )
    if not isinstance(bundle, dict):
        raise TypeError("Evaluation dataset adapter_specs must be an object")
    validate_adapter_specs(bundle, scenarios)
    return bundle


def adapter_scenarios(
    bundle: dict[str, Any], adapter: str
) -> list[dict[str, Any]]:
    section = bundle.get(adapter)
    if not isinstance(section, dict):
        raise TypeError(
            f"Canonical adapter specs require an '{adapter}' object"
        )
    scenarios = section.get("scenarios")
    if not isinstance(scenarios, list):
        raise TypeError(
            f"Canonical {adapter} adapter specs require a scenarios list"
        )
    return scenarios
