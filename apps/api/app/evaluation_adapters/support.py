import asyncio
import os
import re
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import yaml

from ..prompts import agent_tool_budgets, render_agent_system_prompt, render_prompt


def agent_markdown(
    agent: dict[str, Any],
    *,
    include_copilot_tools: bool = True,
    task_mode: str = "change",
) -> str:
    tool_for_capability = {
        "repository.read": "read", "filesystem.read": "read",
        "repository.write": "edit", "filesystem.write": "edit",
        "test.run": "bash", "build.run": "bash", "dependency.install": "bash",
        "git.status": "bash", "git.diff": "bash",
    }
    allowed = [
        tool_for_capability[item]
        for item in agent.get("capabilities", [])
        if item in tool_for_capability
    ]
    frontmatter: dict[str, Any] = {
        "name": "candidate",
        "description": agent.get("description", "Governed Workbench agent candidate"),
    }
    if include_copilot_tools:
        frontmatter["tools"] = sorted(set(allowed))
    max_tool_calls, max_shell_calls = agent_tool_budgets(agent)
    system_prompt = render_agent_system_prompt(
        agent,
        agent_id=str((agent.get("identity") or {}).get("id") or "candidate"),
        task_mode=task_mode,
        max_tool_calls=max_tool_calls,
        max_shell_calls=max_shell_calls,
        runtime="external",
    )
    return render_prompt(
        "evaluator-candidate-agent",
        agent_frontmatter=yaml.safe_dump(frontmatter, sort_keys=False).strip(),
        system_prompt=system_prompt,
        denied=[str(item) for item in agent.get("deny", [])],
    )


def fixture_files(scenario: dict[str, Any]) -> dict[str, str]:
    fixture = scenario.get("fixture") or {}
    files = fixture.get("files") or {}
    return {str(path): str(content) for path, content in files.items()}


def write_fixture(root: Path, scenario: dict[str, Any]) -> Path:
    fixture = root / "fixtures" / str(scenario["id"])
    for relative, content in fixture_files(scenario).items():
        target = (fixture / relative).resolve()
        if fixture.resolve() not in target.parents:
            raise ValueError(f"Fixture path escapes its root: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return fixture


def file_graders(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    checks = scenario.get("checks") or {}
    return [
        {"type": "file-exists", "config": {"path": path}}
        for path in checks.get("required_files", [])
    ]


async def command(
    arguments: list[str], cwd: Path, timeout: int = 1800,
    environment: dict[str, str] | None = None,
    max_output_chars: int = 200_000,
) -> tuple[int, str, float]:
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=cwd,
        env={**os.environ, **(environment or {}),
             "NO_COLOR": "1", "WAZA_NO_UPDATE_CHECK": "1"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name != "nt",
    )

    async def terminate() -> None:
        if process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        await process.wait()

    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        await terminate()
        raise RuntimeError(
            f"{' '.join(arguments[:2])} timed out after {timeout}s"
        ) from None
    except asyncio.CancelledError:
        await terminate()
        raise
    return (
        process.returncode or 0,
        output.decode(errors="replace")[-max_output_chars:],
        time.monotonic() - started,
    )


def openai_provider_url(url: str) -> str:
    normalized = url.rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        line = (result.stdout or result.stderr).strip().splitlines()[0]
        match = re.search(r"\b\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b", line)
        return match.group(0) if match else line
    except (OSError, subprocess.SubprocessError, IndexError):
        return None
