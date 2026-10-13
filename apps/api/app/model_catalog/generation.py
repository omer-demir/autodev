from pathlib import Path
from typing import Any

from agent_framework.github import GitHubCopilotAgent
from agent_framework.ollama import OllamaChatClient

from ..config import get_settings


async def generate_text(
    model: str, instructions: str, prompt: str, provider: str | None = None
) -> str:
    settings = get_settings()
    selected_provider = (provider or settings.model_provider).casefold()
    if selected_provider == "ollama":
        agent = OllamaChatClient(host=settings.ollama_url, model=model).as_agent(
            instructions=instructions, default_options={"model": model}
        )
    elif selected_provider == "copilot":
        options: dict[str, Any] = {
            "cli_path": settings.copilot_cli_path,
            "timeout": float(settings.model_request_timeout_seconds),
            "base_directory": str(Path(settings.copilot_home).expanduser().resolve()),
            "enable_file_hooks": False,
            "available_tools": [],
        }
        if model not in {"", "auto"}:
            options["model"] = model
        agent = GitHubCopilotAgent(
            instructions=instructions, default_options=options)
    else:
        raise RuntimeError(f"Unsupported model provider: {selected_provider}")
    async with agent:
        response = await agent.run(prompt)
    return response.text
