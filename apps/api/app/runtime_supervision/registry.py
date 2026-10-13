from functools import lru_cache
from importlib import import_module
from importlib.metadata import entry_points
from typing import Any

from .errors import SupervisionConfigurationError
from .provider import RuntimeSupervisorProvider


@lru_cache
def get_runtime_supervisor_provider() -> RuntimeSupervisorProvider:
    from ..config import get_settings
    from .providers import LocalRuntimeSupervisor, MicrosoftAgentHypervisorProvider

    provider_name = get_settings().runtime_supervisor_provider.strip()
    if provider_name == "local":
        return LocalRuntimeSupervisor()
    if provider_name in {"microsoft", "microsoft_agent_hypervisor"}:
        return MicrosoftAgentHypervisorProvider()

    matching = [
        item
        for item in entry_points(group="autodev.runtime_supervisors")
        if item.name == provider_name
    ]
    if matching:
        return _provider_instance(matching[0].load(), provider_name)
    if ":" in provider_name:
        module_name, attribute_name = provider_name.split(":", 1)
        return _provider_instance(
            getattr(import_module(module_name), attribute_name),
            provider_name,
        )
    raise SupervisionConfigurationError(
        f"Unknown runtime supervisor provider: {provider_name}"
    )


def _provider_instance(candidate: Any, provider_name: str) -> RuntimeSupervisorProvider:
    instance = candidate() if callable(candidate) else candidate
    if not isinstance(instance, RuntimeSupervisorProvider):
        raise SupervisionConfigurationError(
            f"Runtime supervisor provider {provider_name} does not implement the provider contract"
        )
    return instance
