import asyncio
import json
import os
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .prompts import render_prompt


@dataclass(frozen=True)
class AdapterResult:
    adapter: str
    passed: bool
    score: float
    duration_seconds: float
    results: list[dict[str, Any]]
    metrics: dict[str, Any]
    evidence_path: str
    version: str | None = None
    error: str | None = None


class EvaluationAdapter(ABC):
    """External evaluator boundary with normalized, evidence-linked results."""

    name: str

    @abstractmethod
    async def run(
        self,
        *,
        dataset: dict[str, Any],
        agent: dict[str, Any],
        model_name: str,
        output_dir: Path,
    ) -> AdapterResult: ...


def _agent_markdown(agent: dict[str, Any], *, include_copilot_tools: bool = True) -> str:
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
    return render_prompt(
        "evaluator-candidate-agent",
        agent_frontmatter=yaml.safe_dump(frontmatter, sort_keys=False).strip(),
        description=str(agent.get("description", "")),
        denied=[str(item) for item in agent.get("deny", [])],
    )


def _fixture_files(scenario: dict[str, Any]) -> dict[str, str]:
    fixture = scenario.get("fixture") or {}
    files = fixture.get("files") or {}
    return {str(path): str(content) for path, content in files.items()}


def _write_fixture(root: Path, scenario: dict[str, Any]) -> Path:
    fixture = root / "fixtures" / str(scenario["id"])
    for relative, content in _fixture_files(scenario).items():
        target = (fixture / relative).resolve()
        if fixture.resolve() not in target.parents:
            raise ValueError(f"Fixture path escapes its root: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return fixture


def _file_graders(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    checks = scenario.get("checks") or {}
    return [
        {"type": "file-exists", "config": {"path": path}}
        for path in checks.get("required_files", [])
    ]


async def _command(arguments: list[str], cwd: Path, timeout: int = 1800) -> tuple[int, str, float]:
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=cwd,
        env={**os.environ, "NO_COLOR": "1", "WAZA_NO_UPDATE_CHECK": "1"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(
            f"{' '.join(arguments[:2])} timed out after {timeout}s") from None
    return process.returncode or 0, output.decode(errors="replace")[-200_000:], time.monotonic() - started


def _version(executable: str) -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            [executable, "--version"], text=True, capture_output=True, timeout=10, check=False
        )
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def _numbers(value: Any, keys: set[str]) -> list[float]:
    found: list[float] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in keys and isinstance(item, (int, float)):
                found.append(float(item))
            found.extend(_numbers(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(_numbers(item, keys))
    return found


class VallyAdapter(EvaluationAdapter):
    name = "vally"

    async def run(
        self,
        *,
        dataset: dict[str, Any],
        agent: dict[str, Any],
        model_name: str,
        output_dir: Path,
    ) -> AdapterResult:
        executable = shutil.which("vally")
        if not executable:
            raise RuntimeError(
                "Vally CLI is not installed; install @microsoft/vally-cli")
        root = output_dir / self.name
        root.mkdir(parents=True, exist_ok=True)
        agent_file = root / "candidate.agent.md"
        agent_file.write_text(_agent_markdown(agent), encoding="utf-8")
        specs: list[Path] = []
        for scenario in dataset["scenarios"]:
            fixture = _write_fixture(root, scenario)
            graders = _file_graders(scenario)
            checks = scenario.get("checks") or {}
            if checks.get("tests_required"):
                graders.append(
                    {"type": "run-command", "config": {"command": checks.get("test_command", "python3 -m pytest -q")}})
            if not graders:
                graders.append(
                    {"type": "output-contains", "config": {"substring": "completed", "case_sensitive": False}})
            defaults: dict[str, Any] = {
                "runs": 1, "timeout": "10m", "executor": "copilot-sdk"
            }
            if model_name not in {"", "auto"}:
                defaults["model"] = model_name
            spec = {
                "name": f"workbench-{scenario['id']}",
                "version": dataset.get("content_hash", "unfrozen")[:12],
                "type": "regression",
                "defaults": defaults,
                "agent_environment": {
                    "files": [
                        {"src": str(fixture), "dest": "."},
                        {"src": str(agent_file),
                         "dest": ".github/agents/candidate.agent.md"},
                    ]
                },
                "stimuli": [{
                    "name": scenario["id"],
                    "prompt": render_prompt(
                        "vally-delegation", scenario_prompt=str(scenario["prompt"])
                    ),
                    "graders": graders,
                    "rubric": scenario.get("rubric", []),
                    "constraints": {"max_turns": 40, "max_duration": "10m"},
                }],
                "scoring": {"threshold": float(checks.get("minimum_score", 0.8))},
            }
            path = root / f"{scenario['id']}.eval.yaml"
            path.write_text(yaml.safe_dump(
                spec, sort_keys=False), encoding="utf-8")
            specs.append(path)
        results_root = root / "results"
        arguments = [executable, "eval"]
        for spec in specs:
            arguments.extend(["--eval-spec", str(spec)])
        arguments.extend(["--output-dir", str(results_root),
                         "--output", "jsonl", "--require-pass", "--workers", "1"])
        code, output, duration = await _command(arguments, root)
        (root / "console.log").write_text(output, encoding="utf-8")
        records: list[dict[str, Any]] = []
        for line in output.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        scores = _numbers(records, {"score", "overallscore", "overall_score"})
        score = sum(scores) / len(scores) if scores else float(code == 0)
        return AdapterResult(
            self.name, code == 0, round(score, 4), round(duration, 3), records,
            {"exit_code": code, "records": len(records)}, str(
                root), _version(executable),
            None if code == 0 else output[-4000:],
        )


class WazaAdapter(EvaluationAdapter):
    name = "waza"

    async def run(
        self,
        *,
        dataset: dict[str, Any],
        agent: dict[str, Any],
        model_name: str,
        output_dir: Path,
    ) -> AdapterResult:
        executable = shutil.which("waza")
        if not executable:
            raise RuntimeError(
                "Waza CLI is not installed; install the Microsoft Waza binary")
        root = output_dir / self.name
        root.mkdir(parents=True, exist_ok=True)
        normalized: list[dict[str, Any]] = []
        started = time.monotonic()
        all_passed = True
        for scenario in dataset["scenarios"]:
            scenario_root = root / str(scenario["id"])
            scenario_root.mkdir(parents=True, exist_ok=True)
            (scenario_root / "candidate.agent.md").write_text(
                _agent_markdown(agent, include_copilot_tools=False), encoding="utf-8"
            )
            fixture = _write_fixture(scenario_root, scenario)
            task_dir = scenario_root / "tasks"
            task_dir.mkdir(parents=True, exist_ok=True)
            task = {
                "id": scenario["id"],
                "name": scenario.get("name", scenario["id"]),
                "description": scenario.get("description", scenario["prompt"]),
                "inputs": {
                    "prompt": scenario["prompt"],
                    "files": [{"path": path} for path in _fixture_files(scenario)],
                },
            }
            (task_dir / "task.yaml").write_text(yaml.safe_dump(task,
                                                               sort_keys=False), encoding="utf-8")
            graders: list[dict[str, Any]] = []
            for path in (scenario.get("checks") or {}).get("required_files", []):
                graders.append({
                    "type": "file", "name": f"file-{path}",
                    "config": {"must_exist": [path]},
                })
            if not graders:
                graders.append({"type": "behavior", "name": "bounded-run",
                               "config": {"max_tool_calls": 40, "max_duration_ms": 600000}})
            config: dict[str, Any] = {
                "trials_per_task": 1, "timeout_seconds": 600,
                "executor": "copilot-sdk", "parallel": False,
            }
            if model_name not in {"", "auto"}:
                config["model"] = model_name
            spec = {
                "name": f"workbench-{scenario['id']}",
                "skill": "candidate",
                "schemaVersion": "1.0",
                "version": dataset.get("content_hash", "unfrozen")[:12],
                "config": config,
                "graders": graders,
                "tasks": ["tasks/*.yaml"],
            }
            spec_path = scenario_root / "eval.yaml"
            spec_path.write_text(yaml.safe_dump(
                spec, sort_keys=False), encoding="utf-8")
            result_path = scenario_root / "results.json"
            code, output, _ = await _command(
                [executable, "run", str(
                    spec_path), "--context-dir", str(fixture), "--output", str(result_path), "--no-cache"],
                scenario_root,
            )
            (scenario_root / "console.log").write_text(output, encoding="utf-8")
            parsed: dict[str, Any] = {}
            if result_path.exists():
                try:
                    parsed = json.loads(
                        result_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    parsed = {}
            normalized.append(
                {"scenario_id": scenario["id"], "passed": code == 0, "exit_code": code, "result": parsed})
            all_passed = all_passed and code == 0
        scores = _numbers(
            normalized, {"score", "overallscore", "overall_score", "avg_score"})
        score = sum(scores) / len(scores) if scores else sum(
            item["passed"] for item in normalized) / max(1, len(normalized))
        duration = time.monotonic() - started
        return AdapterResult(
            self.name, all_passed, round(
                score, 4), round(duration, 3), normalized,
            {"scenarios": len(normalized)}, str(root), _version(executable),
            None if all_passed else "One or more Waza scenarios failed; see adapter evidence.",
        )


def get_adapter(name: str) -> EvaluationAdapter:
    adapters: dict[str, type[EvaluationAdapter]] = {
        "vally": VallyAdapter, "waza": WazaAdapter}
    try:
        return adapters[name.casefold()]()
    except KeyError:
        raise ValueError(f"Unsupported evaluation adapter: {name}") from None
