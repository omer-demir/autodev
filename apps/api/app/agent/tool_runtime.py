import json
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..harness import resolve_agent_harness, resolved_tools
from ..providers import Decision, GovernanceProvider, SandboxProvider
from ..runtime_supervision import SupervisionDeniedError
from ..workflow_supervisor import WorkflowSupervisor
from .command_policy import classify, supervised_action
from .repository import (
    EXCLUDED_PARTS,
    read_file_chunk,
    repository_files,
    safe_path,
    search_repository_text,
)
from .types import EventCallback


_SENSITIVE_ARGUMENT = re.compile(
    r"(?:token|secret|password|passwd|authorization|credential|api[_-]?key)",
    re.IGNORECASE,
)


def _command_summary(arguments: Any) -> str:
    values = [str(item)
              for item in arguments] if isinstance(arguments, list) else []
    redacted: list[str] = []
    redact_next = False
    for value in values[:40]:
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        key, separator, _ = value.partition("=")
        if separator and _SENSITIVE_ARGUMENT.search(key):
            redacted.append(f"{key}=[REDACTED]")
            continue
        redacted.append(value)
        if value.startswith("-") and _SENSITIVE_ARGUMENT.search(value):
            redact_next = True
    return f"Command: {shlex.join(redacted)[:500]}"


def _tool_request_summary(name: str, arguments: dict[str, Any]) -> str:
    path = str(arguments.get("path") or ".")[:300]
    if name == "run_command":
        return _command_summary(arguments.get("arguments"))
    if name == "write_file":
        content = str(arguments.get("content") or "")
        return f"Path: {path} · proposed content: {len(content)} characters"
    if name == "delete_file":
        return f"Path: {path}"
    if name == "read_repository_file":
        return (
            f"Path: {path} · offset {int(arguments.get('offset', 0))} · "
            f"limit {int(arguments.get('limit', 6000))}"
        )
    if name == "search_text":
        query = str(arguments.get("query") or "")[:160]
        pattern = str(arguments.get("pattern") or "*")[:120]
        return f"Search: {query!r} · path {path} · pattern {pattern}"
    if name == "list_files":
        pattern = str(arguments.get("pattern") or "*")[:120]
        return f"Path: {path} · pattern {pattern}"
    return "Governed workspace tool request"


@dataclass
class ToolRuntime:
    task_id: str
    agent_id: str
    workspace: Path
    container_id: str
    callback: EventCallback
    sandbox: SandboxProvider
    governance: GovernanceProvider
    supervisor: WorkflowSupervisor
    tool_definitions: dict[str, dict[str, Any]] | None = None
    max_tool_invocations: int = 40
    max_shell_invocations: int = 40
    invocation_count: int = 0
    shell_invocation_count: int = 0

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # Copilot also registers a built-in named read_file whose argument
        # contract conflicts with the Workbench tool. Models use the unique
        # read_repository_file name; retain read_file for MCP and queued jobs
        # created before harness 1.1.0.
        resolved_name = (
            "read_repository_file" if name == "read_file" else name
        )
        self.invocation_count += 1
        if self.invocation_count > self.max_tool_invocations:
            raise RuntimeError(
                f"Agent exceeded the policy limit of {self.max_tool_invocations} tool invocations"
            )
        if resolved_name == "run_command":
            self.shell_invocation_count += 1
            if self.shell_invocation_count > self.max_shell_invocations:
                raise RuntimeError(
                    f"Agent exceeded the policy limit of {self.max_shell_invocations} shell invocations"
                )
        started = time.monotonic()
        tools = self.tool_definitions or resolved_tools(
            resolve_agent_harness(self.agent_id))
        tool = tools.get(resolved_name)
        request_data = {
            "tool": resolved_name,
            "tool_description": str(
                tool.get("description")
                if tool and tool.get("description")
                else "Governed workspace operation"
            )[:300],
            "request_summary": _tool_request_summary(resolved_name, arguments),
        }
        await self.callback(
            "tool.requested",
            resolved_name,
            request_data["request_summary"],
            "info",
            request_data,
        )
        capability = str(tool.get("capability")) if tool and tool.get(
            "capability") else None
        if tool and tool.get("capability_resolver") == "command-v1":
            capability = classify(arguments.get("arguments", []))
        if not capability:
            await self.callback(
                "tool.denied",
                f"{resolved_name} denied by governance boundary",
                "Only governed test, build, dependency, and read-only Git commands are allowed",
                "error",
                {**request_data, "capability": None, "decision": "DENY"},
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
            {
                **request_data,
                "capability": capability,
                "decision": decision.decision,
                "policy": decision.policy,
            },
        )
        if decision.decision != Decision.ALLOW:
            raise PermissionError(decision.reason)

        try:
            supervision = await self.supervisor.before_action(
                self.task_id,
                supervised_action(capability, arguments),
                agent_id=self.agent_id,
            )
        except SupervisionDeniedError as exc:
            denied = exc.decision
            await self.callback(
                "runtime_supervision.denied",
                f"{resolved_name} denied by runtime supervisor",
                denied.reason,
                "error",
                {
                    **request_data,
                    "provider": denied.provider,
                    "capability": capability,
                    "agent_tier": denied.agent_tier.value,
                    "required_tier": denied.required_tier.value,
                    **denied.evidence,
                },
            )
            raise PermissionError(denied.reason) from exc
        except Exception as exc:
            await self.callback(
                "runtime_supervision.error",
                f"{capability} failed closed at runtime supervisor",
                type(exc).__name__,
                "error",
                {
                    **request_data,
                    "provider": self.supervisor.provider.provider_id,
                    "capability": capability,
                    "decision": "DENY",
                },
            )
            raise PermissionError(
                f"Runtime supervision failed closed: {type(exc).__name__}"
            ) from exc
        await self.callback(
            "runtime_supervision.allowed",
            f"{capability} allowed by runtime supervisor",
            supervision.reason,
            "info",
            {
                "provider": supervision.provider,
                "capability": capability,
                "agent_tier": supervision.agent_tier.value,
                "required_tier": supervision.required_tier.value,
                **supervision.evidence,
            },
        )

        if resolved_name == "list_files":
            root = safe_path(self.workspace, str(arguments.get("path", ".")))
            if not root.is_dir():
                raise ValueError("Directory does not exist")
            if EXCLUDED_PARTS.intersection(root.relative_to(self.workspace).parts):
                raise ValueError(
                    "Generated dependency directories cannot be listed")
            offset = int(arguments.get("offset", 0))
            limit = int(arguments.get("limit", 200))
            if offset < 0 or limit < 1 or limit > 300:
                raise ValueError("File list offset or limit is invalid")
            paths = repository_files(root, str(arguments.get("pattern", "*")))
            files = [
                str(path.relative_to(self.workspace))
                for path in paths[offset:offset + limit]
            ]
            next_offset = offset + len(files)
            result: dict[str, Any] = {
                "files": files,
                "offset": offset,
                "next_offset": next_offset if next_offset < len(paths) else None,
                "total_files": len(paths),
                "truncated": next_offset < len(paths),
            }
        elif resolved_name == "search_text":
            root = safe_path(self.workspace, str(arguments.get("path", ".")))
            if not root.exists():
                raise ValueError("Search path does not exist")
            if EXCLUDED_PARTS.intersection(root.relative_to(self.workspace).parts):
                raise ValueError(
                    "Generated dependency directories cannot be searched")
            result = search_repository_text(
                self.workspace,
                root,
                str(arguments["query"]),
                str(arguments.get("pattern", "*")),
                int(arguments.get("max_matches", 50)),
            )
        elif resolved_name == "read_repository_file":
            path = safe_path(self.workspace, str(arguments["path"]))
            result = read_file_chunk(
                path,
                str(arguments["path"]),
                int(arguments.get("offset", 0)),
                int(arguments.get("limit", 6000)),
            )
        elif resolved_name == "write_file":
            path = safe_path(self.workspace, str(arguments["path"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(arguments["content"])
            path.write_text(content, encoding="utf-8")
            result = {"path": str(
                arguments["path"]), "bytes": len(content.encode())}
        elif resolved_name == "delete_file":
            path = safe_path(self.workspace, str(arguments["path"]))
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
