from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic SDLC Workbench"
    database_url: str = "sqlite:///./workbench.db"
    execution_mode: str = "real"
    governance_provider: str = "agent_os"
    model_provider: str = "copilot"
    model_name: str = "auto"
    model_fallback_provider: str = "ollama"
    model_fallback_name: str = "gemma4:e2b"
    model_pricing_json: str = "{}"
    foundry_responses_endpoint: str | None = None
    foundry_model: str = "gpt-5.4-mini"
    foundry_reasoning_summary: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    copilot_home: str = "~/.copilot"
    copilot_cli_path: str = "copilot"
    evidence_dir: str = ".evidence"
    workspace_dir: str = ".workspaces"
    docker_executable: str = "docker"
    docker_workspace_host: str | None = None
    sandbox_image: str = "agentic-sdlc-sandbox:local"
    sandbox_provider: str = "docker"
    azure_session_pool_endpoint: str | None = None
    azure_session_pool_network_mode: str = "none"
    azure_session_pool_profile: str = "python-hyperv-2cpu-2gi-egress"
    azure_session_pool_cpu_limit: float = 2.0
    azure_session_pool_memory_mb: int = 2048
    github_token: str | None = None
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    github_oauth_scope: str = "read:user repo"
    auth_mode: str = "local"
    local_user_id: str = "local-admin"
    local_organization_id: str = "local"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_algorithms: str = "RS256,ES256"
    oidc_organization_claim: str = "org_id"
    oidc_roles_claim: str = "roles"
    oidc_auto_provision: bool = True
    agent_identity_dir: str = ".agentmesh"
    web_app_url: str = "http://localhost:3000"
    web_editor_url: str | None = None
    mcp_allowed_hosts: str = "localhost,localhost:8000,127.0.0.1,127.0.0.1:8000,api,api:8000,testserver"
    mcp_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_agent_steps: int = 40
    model_request_timeout_seconds: int = 300
    agent_turn_timeout_seconds: int = 1800
    model_recovery_timeout_seconds: int = 600
    runtime_discovery_timeout_seconds: int = 10
    sandbox_command_timeout_seconds: int = 1800
    agent_sre_enabled: bool = True
    agent_sre_task_success_target: float = 0.95
    agent_sre_error_budget: float = 1.0
    prompt_defense_min_grade: str = "C"
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "autodev-api"
    model_config = SettingsConfigDict(
        env_prefix="WORKBENCH_", env_file=".env", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
