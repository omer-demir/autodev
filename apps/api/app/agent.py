from __future__ import annotations

import asyncio
import json
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_framework import AgentResponse, FunctionInvocationContext, tool
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from agent_framework.ollama import OllamaChatClient
from copilot.rpc import PermissionDecisionApproveOnce, PermissionDecisionUserNotAvailable
from copilot.session_events import PermissionRequestCustomTool

from .config import get_settings
from .foundry import FoundryResponsesProvider
from .harness import foundry_tool_schemas, resolve_agent_harness, resolved_tools
from .model_recovery import ModelRecoveryDecision
from .prompts import render_agent_system_prompt, render_prompt
from .providers import (
    Decision,
    GovernanceProvider,
    SandboxProvider,
    get_governance_provider,
    get_sandbox_provider,
)
from .registry import get_definition

EventCallback = Callable[[str, str, str, str,
                          dict[str, Any] | None], Awaitable[None]]
SteeringProvider = Callable[[], Awaitable[list[str]]]
ModelRecovery = Callable[[str, str, int], Awaitable[ModelRecoveryDecision]]

_EXCLUDED_PARTS = {".git", "node_modules", ".venv", "dist", "build"}
_WORKBENCH_TOOL_NAMES = {
    "list_files", "search_text", "read_file", "write_file", "delete_file", "run_command",
}


class _ModelRecoveryRedirect(Exception):
    def __init__(self, decision: ModelRecoveryDecision, error: str) -> None:
        super().__init__(error)
        self.decision = decision
        self.error = error


def _copilot_permission_handler(request: Any, _context: Any) -> Any:
    """Permit the SDK to dispatch Workbench tools to our governance boundary."""
    del _context
    if (
        isinstance(request, PermissionRequestCustomTool)
        and request.tool_name in _WORKBENCH_TOOL_NAMES
    ):
        return PermissionDecisionApproveOnce()
    return PermissionDecisionUserNotAvailable()


def _safe_path(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError("Path escapes the repository workspace")
    if ".git" in candidate.relative_to(workspace).parts:
        raise ValueError("Direct access to .git is not allowed")
    return candidate


def _classify(arguments: list[str]) -> str | None:
    if not arguments:
        return None
    executable = Path(arguments[0]).name
    subcommand = arguments[1] if len(arguments) > 1 else ""
    if executable == "git" and subcommand in {"status", "diff", "log", "show"}:
        return f"git.{subcommand if subcommand in {'status', 'diff'} else 'diff'}"
    if (
        executable == "pytest"
        or arguments[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
        or (executable == "go" and subcommand == "test")
        or (executable == "cargo" and subcommand == "test")
        or (executable == "dotnet" and subcommand == "test")
        or (executable in {"mvn", "mvnw", "gradle", "gradlew"} and "test" in arguments[1:])
        or arguments[:2] in (["npm", "test"], ["pnpm", "test"], ["yarn", "test"])
        or (arguments[:2] == ["bundle", "exec"] and len(arguments) > 2
            and arguments[2] in {"rspec", "rake"})
    ):
        return "test.run"
    if (
        (executable in {"npm", "pnpm", "yarn", "pip", "pip3", "poetry", "uv"}
         and subcommand in {"install", "ci", "add", "sync", "update"})
        or (executable in {"python", "python3"} and arguments[1:3] == ["-m", "pip"]
            and len(arguments) > 3 and arguments[3] == "install")
        or (executable == "go" and arguments[1:3] in (["mod", "download"], ["mod", "tidy"]))
        or (executable == "go" and subcommand == "get")
        or (executable == "cargo" and subcommand in {"fetch", "update", "add"})
        or (executable == "bundle" and subcommand == "install")
        or (executable == "composer" and subcommand in {"install", "update"})
        or (executable == "dotnet" and subcommand in {"restore", "add"})
        or (executable in {"mvn", "mvnw"} and "dependency:go-offline" in arguments[1:])
    ):
        return "dependency.install"
    if executable in {
        "npm", "pnpm", "yarn", "make", "go", "cargo", "python", "python3",
        "dotnet", "mvn", "mvnw", "gradle", "gradlew", "bundle", "composer",
    }:
        return "build.run"
    return None


def _read_file_chunk(path: Path, relative: str, offset: int = 0, limit: int = 6000) -> dict[str, Any]:
    if offset < 0:
        raise ValueError("File offset must be non-negative")
    if limit < 1 or limit > 24000:
        raise ValueError(
            "File read limit must be between 1 and 24000 characters")
    content = path.read_text(encoding="utf-8")
    chunk = content[offset:offset + limit]
    next_offset = offset + len(chunk)
    return {
        "path": relative,
        "content": chunk,
        "offset": offset,
        "next_offset": next_offset if next_offset < len(content) else None,
        "total_chars": len(content),
        "truncated": next_offset < len(content),
    }


def _looks_taskless(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    return any(phrase in normalized for phrase in (
        "please provide the task",
        "provide the task you would like",
        "what task would you like",
        "what would you like me to do",
    ))


def _repository_files(root: Path, pattern: str = "*") -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if pattern != "*" and not relative.match(pattern):
            continue
        files.append(path)
        if len(files) >= 10000:
            break
    return sorted(files, key=lambda item: str(item.relative_to(root)))


def _search_repository_text(
    workspace: Path, root: Path, query: str, pattern: str = "*", max_matches: int = 50
) -> dict[str, Any]:
    if not query:
        raise ValueError("Search query must not be empty")
    max_matches = min(max(max_matches, 1), 200)
    needle = query.casefold()
    matches: list[dict[str, Any]] = []
    scanned = 0
    files = [root] if root.is_file() else _repository_files(root, pattern)
    for path in files:
        if path.stat().st_size > 1_000_000:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for line_number, line in enumerate(lines, 1):
            if needle in line.casefold():
                matches.append({
                    "path": str(path.relative_to(workspace)),
                    "line": line_number,
                    "text": line[:500],
                })
                if len(matches) >= max_matches:
                    return {"matches": matches, "truncated": True, "files_scanned": scanned}
    return {"matches": matches, "truncated": False, "files_scanned": scanned}


@dataclass
class ToolRuntime:
    task_id: str
    agent_id: str
    workspace: Path
    container_id: str
    callback: EventCallback
    sandbox: SandboxProvider
    governance: GovernanceProvider
    tool_definitions: dict[str, dict[str, Any]] | None = None
    max_tool_invocations: int = 40
    max_shell_invocations: int = 40
    invocation_count: int = 0
    shell_invocation_count: int = 0

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.invocation_count += 1
        if self.invocation_count > self.max_tool_invocations:
            raise RuntimeError(
                f"Agent exceeded the policy limit of {self.max_tool_invocations} tool invocations"
            )
        if name == "run_command":
            self.shell_invocation_count += 1
            if self.shell_invocation_count > self.max_shell_invocations:
                raise RuntimeError(
                    f"Agent exceeded the policy limit of {self.max_shell_invocations} shell invocations"
                )
        await self.callback(
            "tool.requested", name, json.dumps(arguments, ensure_ascii=False)[
                :2000], "info", None
        )
        started = time.monotonic()
        tools = self.tool_definitions or resolved_tools(
            resolve_agent_harness(self.agent_id))
        tool = tools.get(name)
        capability = str(tool.get("capability")) if tool and tool.get(
            "capability") else None
        if tool and tool.get("capability_resolver") == "command-v1":
            capability = _classify(arguments.get("arguments", []))
        if not capability:
            await self.callback(
                "tool.denied",
                "Command denied by governance boundary",
                "Only governed test, build, dependency, and read-only Git commands are allowed",
                "error",
                {"capability": None, "decision": "DENY", "arguments": arguments},
            )
            raise ValueError(
                "Command is outside the governed test/build/dependency/read-only Git allowlist"
            )
        decision = await self.governance.evaluate(
            self.agent_id, capability, arguments, {"task_id": self.task_id}
        )
        await self.callback(
            "tool.allowed" if decision.decision == Decision.ALLOW else "tool.denied",
            f"{capability} {decision.decision}",
            decision.reason,
            "info" if decision.decision == Decision.ALLOW else "error",
            {"capability": capability, "decision": decision.decision,
                "policy": decision.policy},
        )
        if decision.decision != Decision.ALLOW:
            raise PermissionError(decision.reason)

        if name == "list_files":
            root = _safe_path(self.workspace, str(arguments.get("path", ".")))
            if not root.is_dir():
                raise ValueError("Directory does not exist")
            if _EXCLUDED_PARTS.intersection(root.relative_to(self.workspace).parts):
                raise ValueError(
                    "Generated dependency directories cannot be listed")
            offset = int(arguments.get("offset", 0))
            limit = int(arguments.get("limit", 200))
            if offset < 0 or limit < 1 or limit > 300:
                raise ValueError("File list offset or limit is invalid")
            paths = _repository_files(root, str(arguments.get("pattern", "*")))
            files = [str(path.relative_to(self.workspace))
                     for path in paths[offset:offset + limit]]
            next_offset = offset + len(files)
            result: dict[str, Any] = {
                "files": files,
                "offset": offset,
                "next_offset": next_offset if next_offset < len(paths) else None,
                "total_files": len(paths),
                "truncated": next_offset < len(paths),
            }
        elif name == "search_text":
            root = _safe_path(self.workspace, str(arguments.get("path", ".")))
            if not root.exists():
                raise ValueError("Search path does not exist")
            if _EXCLUDED_PARTS.intersection(root.relative_to(self.workspace).parts):
                raise ValueError(
                    "Generated dependency directories cannot be searched")
            result = _search_repository_text(
                self.workspace,
                root,
                str(arguments["query"]),
                str(arguments.get("pattern", "*")),
                int(arguments.get("max_matches", 50)),
            )
        elif name == "read_file":
            path = _safe_path(self.workspace, str(arguments["path"]))
            result = _read_file_chunk(
                path,
                str(arguments["path"]),
                int(arguments.get("offset", 0)),
                int(arguments.get("limit", 6000)),
            )
        elif name == "write_file":
            path = _safe_path(self.workspace, str(arguments["path"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(arguments["content"])
            path.write_text(content, encoding="utf-8")
            result = {"path": str(
                arguments["path"]), "bytes": len(content.encode())}
        elif name == "delete_file":
            path = _safe_path(self.workspace, str(arguments["path"]))
            path.unlink()
            result = {"path": str(arguments["path"]), "deleted": True}
        else:
            command = [str(item) for item in arguments["arguments"]]
            command_started = time.monotonic()
            execution = await self.sandbox.execute_args(
                self.container_id,
                command,
                network_access=capability == "dependency.install",
            )
            result = {
                "arguments": [shlex.join(command)],
                "duration": round(time.monotonic() - command_started, 2),
                **execution,
            }
        await self.callback(
            "tool.completed",
            name,
            json.dumps(result, ensure_ascii=False)[:4000],
            "info",
            {
                "tool": name,
                "capability": capability,
                "latency_ms": round((time.monotonic() - started) * 1000),
                **({"result": result} if capability == "test.run" else {}),
            },
        )
        return result


def _runtime(ctx: FunctionInvocationContext) -> ToolRuntime:
    runtime = ctx.kwargs.get("workbench_runtime")
    if not isinstance(runtime, ToolRuntime):
        raise TypeError("Workbench tool runtime was not provided")
    return runtime


@tool(approval_mode="never_require")
async def list_files(
    path: str = ".", pattern: str = "*", offset: int = 0, limit: int = 200,
    *, ctx: FunctionInvocationContext,
) -> str:
    """List a bounded, sorted page of repository files."""
    return json.dumps(await _runtime(ctx).execute("list_files", {
        "path": path, "pattern": pattern, "offset": offset, "limit": limit,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def search_text(
    query: str, path: str = ".", pattern: str = "*", max_matches: int = 50,
    *, ctx: FunctionInvocationContext,
) -> str:
    """Search a repository file or directory literally; max_matches is clamped to 1..200."""
    return json.dumps(await _runtime(ctx).execute("search_text", {
        "query": query, "path": path, "pattern": pattern, "max_matches": max_matches,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def read_file(
    path: str, offset: int = 0, limit: int = 6000, *, ctx: FunctionInvocationContext,
) -> str:
    """Read a bounded UTF-8 text chunk; use next_offset to continue large files."""
    return json.dumps(await _runtime(ctx).execute("read_file", {
        "path": path, "offset": offset, "limit": limit,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def write_file(path: str, content: str, *, ctx: FunctionInvocationContext) -> str:
    """Create or replace a UTF-8 text file in the repository."""
    return json.dumps(await _runtime(ctx).execute("write_file", {
        "path": path, "content": content,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def delete_file(path: str, *, ctx: FunctionInvocationContext) -> str:
    """Delete one repository file."""
    return json.dumps(
        await _runtime(ctx).execute("delete_file", {"path": path}), ensure_ascii=False
    )


@tool(approval_mode="never_require")
async def run_command(arguments: list[str], *, ctx: FunctionInvocationContext) -> str:
    """Run an argument-vector test, build, dependency, or read-only Git command; no shell."""
    return json.dumps(
        await _runtime(ctx).execute("run_command", {"arguments": arguments}), ensure_ascii=False
    )


WORKBENCH_TOOLS = [list_files, search_text,
                   read_file, write_file, delete_file, run_command]


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

    def _copilot_agent(
        self, instructions: str, model: str, workspace: Path
    ) -> GitHubCopilotAgent[GitHubCopilotOptions]:
        options: dict[str, Any] = {
            "cli_path": self.settings.copilot_cli_path,
            "timeout": float(self.settings.agent_turn_timeout_seconds),
            "base_directory": str(Path(self.settings.copilot_home).expanduser().resolve()),
            "working_directory": str(workspace),
            "enable_file_hooks": False,
            "on_permission_request": _copilot_permission_handler,
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
                    "model.call", "Model invocation",
                    f"{model} · turn {turn + 1} · attempt {attempt}", "info",
                    {"provider": provider, "model": model, "attempt": attempt,
                     "framework": "microsoft-agent-framework"},
                )
                if verbose_logging:
                    await callback(
                        "model.prompt", "LLM prompt", attempt_prompt[-200_000:], "info",
                        {"provider": provider, "model": model, "verbose": True,
                         "attempt": attempt},
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
                    "model.error", "Model provider failed", error[-20_000:], "warning",
                    {"provider": provider, "model": model, "verbose": False,
                     "attempt": attempt},
                )
                if provider != "copilot" or model_recovery is None:
                    raise failure
                decision = await model_recovery(model, error, attempt)
                if decision.action != "retry":
                    raise _ModelRecoveryRedirect(decision, error) from failure
                await callback(
                    "model.retry", "Model turn retrying with retained session",
                    "Continuing from the last completed tool and timeline step",
                    "info", {"provider": provider, "model": model,
                             "attempt": attempt + 1},
                )
                attempt_prompt = (
                    "Continue from the last completed step in this existing session and workspace. "
                    "Do not repeat tool calls that already completed successfully."
                )
            latency_ms = round((time.monotonic() - started) * 1000)
            response_model = str(
                (response.additional_properties or {}).get("model") or model)
            content = response.text.strip()
            await callback(
                "model.completed", "Model invocation completed", f"{provider} · {response_model}",
                "info", {
                    "provider": provider,
                    "model": response_model,
                    "usage": _usage(response),
                    "fallback": provider == "ollama" and self.settings.model_provider == "copilot",
                    "latency_ms": latency_ms,
                    "framework": "microsoft-agent-framework",
                },
            )
            if verbose_logging:
                await callback(
                    "model.response", "LLM response", content[-200_000:], "info",
                    {"provider": provider, "model": response_model, "verbose": True},
                )
            taskless = bool(content and _looks_taskless(content))
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
                    "agent.response.rejected", "Taskless model response rejected", content,
                    "warning", {"provider": provider, "model": response_model},
                )
                next_prompt = "Continue the assigned task. Do not ask for a task; it is already provided."
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
        steering: list[str] | None = None,
        steering_provider: SteeringProvider | None = None,
        model_recovery: ModelRecovery | None = None,
    ) -> str:
        definition = get_definition(
            "agents", agent_id.removeprefix("did:local:"))["data"]
        policy = get_definition(
            "policies", str(definition.get("policy", "development"))
        )["data"]
        policy_runtime = policy.get("runtime", {})
        max_tool_calls = max(
            1, int(policy_runtime.get("max_tool_calls",
                   self.settings.max_agent_steps))
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
            tool_definitions=resolved_tools(resolve_agent_harness(agent_id)),
            max_tool_invocations=max_tool_calls,
            max_shell_invocations=max_shell_calls,
        )
        await callback(
            "agent.budget", "Agent invocation budget",
            f"{max_tool_calls} tool calls · {max_shell_calls} shell calls",
            "info", {
                "max_tool_calls": max_tool_calls,
                "max_shell_calls": max_shell_calls,
                "policy": str(policy.get("name") or definition.get("policy") or "development"),
            },
        )
        seen_steering = set(steering or [])
        provider = self.settings.model_provider.casefold()
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
                provider="ollama", model=model_name, instructions=instructions, prompt=prompt,
                runtime=runtime, callback=callback, verbose_logging=verbose_logging,
                steering_provider=steering_provider, seen_steering=seen_steering,
                workspace=workspace, max_tool_calls=max_tool_calls,
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
                    provider="copilot", model=selected_model, instructions=instructions,
                    prompt=prompt, runtime=runtime, callback=callback,
                    verbose_logging=verbose_logging, steering_provider=steering_provider,
                    seen_steering=seen_steering, workspace=workspace,
                    max_tool_calls=max_tool_calls, model_recovery=model_recovery,
                )
            except _ModelRecoveryRedirect as recovery:
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
                    "model.error", "Model provider failed", primary_error[-20_000:], "warning",
                    {"provider": "copilot", "model": selected_model, "verbose": False},
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
            "model.fallback", "Model provider fallback",
            f"Copilot model '{selected_model}' failed; attempting Ollama model "
            f"'{fallback_model}'. Primary error: {primary_error}",
            "warning", {"provider": "ollama",
                        "model": fallback_model, "verbose": False},
        )
        try:
            return await self._run_agent(
                provider="ollama", model=fallback_model, instructions=instructions, prompt=prompt,
                runtime=runtime, callback=callback, verbose_logging=verbose_logging,
                steering_provider=steering_provider, seen_steering=seen_steering,
                workspace=workspace, max_tool_calls=max_tool_calls, model_recovery=None,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"GitHub Copilot model '{selected_model}' failed: {primary_error}. "
                f"Ollama fallback model '{fallback_model}' also failed: {fallback_error}"
            ) from fallback_error
