from functools import lru_cache

from ...config import get_settings
from .azure_container_apps import AzureContainerAppsSessionProvider
from .docker import DockerSandboxProvider
from .provider import SandboxProvider


@lru_cache
def get_sandbox_provider() -> SandboxProvider:
    settings = get_settings()
    provider = settings.sandbox_provider.strip().lower()
    if provider == "docker":
        return DockerSandboxProvider()
    if provider in {"azure", "azure-container-apps-session-pool"}:
        if not settings.azure_session_pool_endpoint:
            raise RuntimeError(
                "Azure sandbox is configured but "
                "WORKBENCH_AZURE_SESSION_POOL_ENDPOINT is unset"
            )
        return AzureContainerAppsSessionProvider(
            endpoint=settings.azure_session_pool_endpoint,
            network_mode=settings.azure_session_pool_network_mode,
            pool_profile=settings.azure_session_pool_profile,
            cpu_limit=settings.azure_session_pool_cpu_limit,
            memory_mb=settings.azure_session_pool_memory_mb,
        )
    raise RuntimeError(
        f"Unsupported sandbox provider: {settings.sandbox_provider}")
