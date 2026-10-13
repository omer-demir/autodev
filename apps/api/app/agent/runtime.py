import asyncio
import json
import time
from pathlib import Path
from typing import Any

from agent_framework import AgentResponse
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from agent_framework.ollama import OllamaChatClient

from ..config import get_settings
from ..foundry import FoundryResponsesProvider
from ..harness import foundry_tool_schemas, resolve_agent_harness, resolved_tools
from ..model_recovery import ModelRecoveryDecision
from ..prompts import render_agent_system_prompt, render_prompt
from ..providers import get_governance_provider, get_sandbox_provider
from ..registry import get_definition
from ..workflow_supervisor import workflow_supervisor
from .permissions import copilot_permission_handler
from .recovery_redirect import ModelRecoveryRedirect
from .repository import looks_taskless
from .tool_runtime import ToolRuntime
from .tools import WORKBENCH_TOOLS
from .types import EventCallback, ModelRecovery, SteeringProvider


def _usage(response: AgentResponse[Any]) -> dict[str, int]:
    usage = response.usage_details or {}
    return {
        "input_tokens": int(usage.get("input_token_count") or 0),
        "output_tokens": int(usage.get("output_token_count") or 0),
        "total_tokens": int(usage.get("total_token_count") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_token_count") or 0),
        "cache_write_tokens": int(usage.get("cache_creation_input_token_count") or 0),
        "reasoning_tokens": int(usage.get("reasoning_output_token_count") or 0),
    }


class AgentRuntime:
    """Microsoft Agent Framework runtime with Workbench-governed tools."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.sandbox = get_sandbox_provider()
        self.governance = get_governance_provider()
        self.supervisor = workflow_supervisor

    def _copilot_agent(
        self, instructions: str, model: str, workspace: Path
    ) -> GitHubCopilotAgent[GitHubCopilotOptions]:
        options: dict[str, Any] = {
            "cli_path": self.settings.copilot_cli_path,
            "timeout": float(self.settings.agent_turn_timeout_seconds),
            "base_directory": str(Path(self.settings.copilot_home).expanduser().resolve()),
            "working_directory": str(workspace),
            "enable_file_hooks": False,
            "on_permission_request": copilot_permission_handler,
            "available_tools": [f"custom:{item.name}" for item in WORKBENCH_TOOLS],
        }
        if model not in {"", "auto"}:
            options["model"] = model
        return GitHubCopilotAgent(
            name="autodev-coding-agent",
            description="Governed software development agent",
            instructions=instructions,
            tools=WORKBENCH_TOOLS,
            default_options=options,
        )

    def _ollama_agent(self, instructions: str, model: str, max_tool_calls: int):
        client = OllamaChatClient(
            host=self.settings.ollama_url,
            model=model,
            function_invocation_configuration={
                "max_iterations": max_tool_calls,
                "max_function_calls": max_tool_calls,
            },
        )
        return client.as_agent(
            name="autodev-ollama-agent",
            description="Governed local software development agent",
            instructions=instructions,
            tools=WORKBENCH_TOOLS,
            default_options={"model": model},
        )

    async def _run_agent(
        self,
        *,
        provider: str,
        model: str,
        instructions: str,
        prompt: str,
        runtime: ToolRuntime,
        callback: EventCallback,
        verbose_logging: bool,
        steering_provider: SteeringProvider | None,
        seen_steering: set[str],
        workspace: Path,
        max_tool_calls: int,
        model_recovery: ModelRecovery | None,
    ) -> str:
        agent = (
            self._copilot_agent(instructions, model, workspace)
            if provider == "copilot"
            else self._ollama_agent(instructions, model, max_tool_calls)
        )
        async with agent:
            return await self._run_conversation(
                agent=agent,
                provider=provider,
                model=model,
                prompt=prompt,
                runtime=runtime,
                callback=callback,
                verbose_logging=verbose_logging,
                steering_provider=steering_provider,
                seen_steering=seen_steering,
                model_recovery=model_recovery,
            )

    async def _run_conversation(
        self,
        *,
        agent: Any,
        provider: str,
        model: str,
        prompt: str,
        runtime: ToolRuntime,
        callback: EventCallback,
        verbose_logging: bool,
        steering_provider: SteeringProvider | None,
        seen_steering: set[str],
        model_recovery: ModelRecovery | None,
    ) -> str:
        session = agent.create_session()
        next_prompt = prompt
        for turn in range(self.settings.max_agent_steps):
            attempt = 0
            attempt_prompt = next_prompt
            while True:
                attempt += 1
                await callback(
                    "model.call",
                    "Model invocation",
                    f"{model} · turn {turn + 1} · attempt {attempt}",
                    "info",
                    {
                        "provider": provider,
                        "model": model,
                        "attempt": attempt,
                        "framework": "microsoft-agent-framework",
                    },
                )
                if verbose_logging:
                    await callback(
                        "model.prompt",
                        "LLM prompt",
                        attempt_prompt[-200_000:],
                        "info",
                        {
                            "provider": provider,
                            "model": model,
                            "verbose": True,
                            "attempt": attempt,
                        },
                    )
                started = time.monotonic()
                try:
                    async with asyncio.timeout(self.settings.agent_turn_timeout_seconds):
                        response = await agent.run(
                            attempt_prompt,
                            session=session,
                            function_invocation_kwargs={
                                "workbench_runtime": runtime},
                        )
                    break
                except TimeoutError as exc:
                    error = (
                        "Agent turn timed out after "
                        f"{self.settings.agent_turn_timeout_seconds} seconds"
                    )
                    failure: Exception = RuntimeError(error)
                    failure.__cause__ = exc
                except Exception as exc:
                    error = str(exc)
                    failure = exc
                await callback(
                    "model.error",
                    "Model provider failed",
                    error[-20_000:],
                    "warning",
                    {
                        "provider": provider,
                        "model": model,
                        "verbose": False,
                        "attempt": attempt,
                    },
                )
                if provider != "copilot" or model_recovery is None:
                    raise failure
                decision = await model_recovery(model, error, attempt)
                if decision.action != "retry":
                    raise ModelRecoveryRedirect(decision, error) from failure
                await callback(
                    "model.retry",
                    "Model turn retrying with retained session",
                    "Continuing from the last completed tool and timeline step",
                    "info",
                    {"provider": provider, "model": model, "attempt": attempt + 1},
                )
                attempt_prompt = (
                    "Continue from the last completed step in this existing session and workspace. "
                    "Do not repeat tool calls that already completed successfully."
                )
            latency_ms = round((time.monotonic() - started) * 1000)
            response_model = str(
                (response.additional_properties or {}).get("model") or model
            )
            content = response.text.strip()
            await callback(
                "model.completed",
                "Model invocation completed",
                f"{provider} · {response_model}",
                "info",
                {
                    "provider": provider,
                    "model": response_model,
                    "usage": _usage(response),
                    "fallback": (
                        provider == "ollama"
                        and self.settings.model_provider == "copilot"
                    ),
                    "latency_ms": latency_ms,
                    "framework": "microsoft-agent-framework",
                },
            )
            if verbose_logging:
                await callback(
                    "model.response",
                    "LLM response",
                    content[-200_000:],
                    "info",
                    {"provider": provider, "model": response_model, "verbose": True},
                )
            taskless = bool(content and looks_taskless(content))
            if content and not taskless:
                await callback("agent.message", "Agent", content, "info", None)

            new_steering: list[str] = []
            if steering_provider:
                for instruction in await steering_provider():
                    if instruction not in seen_steering:
                        seen_steering.add(instruction)
                        new_steering.append(instruction)
            if new_steering:
                next_prompt = "Developer steering:\n" + "\n".join(
                    f"- {item}" for item in new_steering
                )
                continue
            if taskless:
                await callback(
                    "agent.response.rejected",
                    "Taskless model response rejected",
                    content,
                    "warning",
                    {"provider": provider, "model": response_model},
                )
                next_prompt = (
                    "Continue the assigned task. Do not ask for a task; it is already provided."
                )
                continue
            return content or "Agent completed without a final message."
        raise RuntimeError(
            f"Agent exceeded the configured {self.settings.max_agent_steps} conversation turns"
        )

    async def run(
        self,
        *,
        task_id: str,
        title: str,
        description: str,
        agent_id: str,
        model_name: str,
        task_mode: str,
        verbose_logging: bool,
        workspace: Path,
        container_id: str,
        callback: EventCallback,
        stage_context: dict[str, Any] | None = None,
        steering: list[str] | None = None,
        session_context: list[str] | None = None,
        steering_provider: SteeringProvider | None = None,
        model_recovery: ModelRecovery | None = None,
        model_provider: str | None = None,
    ) -> str:
        definition = get_definition(
            "agents", agent_id.removeprefix("did:local:")
        )["data"]
        policy = get_definition(
            "policies", str(definition.get("policy", "development"))
        )["data"]
        policy_runtime = policy.get("runtime", {})
        max_tool_calls = max(
            1,
            int(policy_runtime.get("max_tool_calls", self.settings.max_agent_steps)),
        )
        max_shell_calls = max(
            1, int(policy_runtime.get("max_shell_calls", max_tool_calls))
        )
        instructions = render_agent_system_prompt(
            definition,
            agent_id=agent_id,
            task_mode=task_mode,
            max_tool_calls=max_tool_calls,
            max_shell_calls=max_shell_calls,
        )
        prompt = render_prompt(
            "coding-task",
            task_id=task_id,
            title=title,
            description=description,
            stage_context_block=(
                json.dumps(stage_context, indent=2, default=str)[-100_000:]
                if stage_context else ""
            ),
            session_context_block="\n".join(session_context or [])[-100_000:],
            steering_block="\n".join(f"- {item}" for item in steering or []),
        )
        runtime = ToolRuntime(
            task_id=task_id,
            agent_id=agent_id,
            workspace=workspace,
            container_id=container_id,
            callback=callback,
            sandbox=self.sandbox,
            governance=self.governance,
            supervisor=self.supervisor,
            tool_definitions=resolved_tools(resolve_agent_harness(agent_id)),
            max_tool_invocations=max_tool_calls,
            max_shell_invocations=max_shell_calls,
        )
        await callback(
            "agent.budget",
            "Agent invocation budget",
            f"{max_tool_calls} tool calls · {max_shell_calls} shell calls",
            "info",
            {
                "max_tool_calls": max_tool_calls,
                "max_shell_calls": max_shell_calls,
                "policy": str(
                    policy.get("name") or definition.get(
                        "policy") or "development"
                ),
            },
        )
        seen_steering = set(steering or [])
        provider = (model_provider or self.settings.model_provider).casefold()
        if provider == "foundry":
            if not self.settings.foundry_responses_endpoint:
                raise RuntimeError(
                    "Microsoft Foundry is configured but "
                    "WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT is unset"
                )
            selected_model = (
                self.settings.foundry_model
                if model_name in {"", "auto"}
                else model_name
            )
            return await FoundryResponsesProvider(
                endpoint=self.settings.foundry_responses_endpoint,
                model=selected_model,
                reasoning_summary=self.settings.foundry_reasoning_summary,
                tool_schemas=foundry_tool_schemas(
                    resolve_agent_harness(agent_id)),
            ).run(
                instructions=instructions,
                prompt=prompt,
                runtime=runtime,
                callback=callback,
                max_steps=self.settings.max_agent_steps,
                verbose_logging=verbose_logging,
                steering_provider=steering_provider,
                seen_steering=seen_steering,
            )
        if provider == "ollama":
            return await self._run_agent(
                provider="ollama",
                model=model_name,
                instructions=instructions,
                prompt=prompt,
                runtime=runtime,
                callback=callback,
                verbose_logging=verbose_logging,
                steering_provider=steering_provider,
                seen_steering=seen_steering,
                workspace=workspace,
                max_tool_calls=max_tool_calls,
                model_recovery=None,
            )
        if provider != "copilot":
            raise RuntimeError(f"Unsupported model provider: {provider}")

        selected_model = model_name
        attempts = 0
        primary_error = ""
        while True:
            attempts += 1
            try:
                return await self._run_agent(
                    provider="copilot",
                    model=selected_model,
                    instructions=instructions,
                    prompt=prompt,
                    runtime=runtime,
                    callback=callback,
                    verbose_logging=verbose_logging,
                    steering_provider=steering_provider,
                    seen_steering=seen_steering,
                    workspace=workspace,
                    max_tool_calls=max_tool_calls,
                    model_recovery=model_recovery,
                )
            except ModelRecoveryRedirect as recovery:
                primary_error = recovery.error
                decision = recovery.decision
                if decision.action == "change_model" and decision.model:
                    selected_model = decision.model
                    continue
                if decision.action == "cancel":
                    raise RuntimeError(
                        f"Copilot model '{selected_model}' failed and operator cancelled recovery: "
                        f"{primary_error}"
                    ) from recovery
                break
            except Exception as exc:
                primary_error = str(exc)
                await callback(
                    "model.error",
                    "Model provider failed",
                    primary_error[-20_000:],
                    "warning",
                    {
                        "provider": "copilot",
                        "model": selected_model,
                        "verbose": False,
                    },
                )
                decision = (
                    await model_recovery(selected_model, primary_error, attempts)
                    if model_recovery
                    else ModelRecoveryDecision("fallback")
                )
                if decision.action == "retry":
                    continue
                if decision.action == "change_model" and decision.model:
                    selected_model = decision.model
                    continue
                if decision.action == "cancel":
                    raise RuntimeError(
                        f"Copilot model '{selected_model}' failed and operator cancelled recovery: "
                        f"{primary_error}"
                    ) from exc
                break

        if self.settings.model_fallback_provider.casefold() != "ollama":
            raise RuntimeError(
                f"GitHub Copilot model '{selected_model}' failed and no Ollama fallback is enabled: "
                f"{primary_error}"
            )
        fallback_model = self.settings.model_fallback_name
        await callback(
            "model.fallback",
            "Model provider fallback",
            f"Copilot model '{selected_model}' failed; attempting Ollama model "
            f"'{fallback_model}'. Primary error: {primary_error}",
            "warning",
            {"provider": "ollama", "model": fallback_model, "verbose": False},
        )
        try:
            return await self._run_agent(
                provider="ollama",
                model=fallback_model,
                instructions=instructions,
                prompt=prompt,
                runtime=runtime,
                callback=callback,
                verbose_logging=verbose_logging,
                steering_provider=steering_provider,
                seen_steering=seen_steering,
                workspace=workspace,
                max_tool_calls=max_tool_calls,
                model_recovery=None,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"GitHub Copilot model '{selected_model}' failed: {primary_error}. "
                f"Ollama fallback model '{fallback_model}' also failed: {fallback_error}"
            ) from fallback_error
