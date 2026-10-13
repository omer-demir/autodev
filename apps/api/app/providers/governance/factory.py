from ...config import get_settings
from .agent_os import AgentOSGovernanceProvider
from .local import LocalGovernanceProvider
from .provider import GovernanceProvider


def get_governance_provider() -> GovernanceProvider:
    provider = get_settings().governance_provider.strip().lower()
    if provider == "local":
        return LocalGovernanceProvider()
    if provider == "agent_os":
        return AgentOSGovernanceProvider()
    raise RuntimeError(f"Unsupported governance provider: {provider}")
