import copy
import re
from pathlib import PurePosixPath
from typing import Any

from ..evaluation_terms import output_term_pattern, term_alternatives
from ..prompts import render_prompt
from .support import agent_markdown, file_graders


def _fixture(scenario: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(scenario.get("fixture") or {"files": {}})


def _vally_graders(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    graders = file_graders(scenario)
    checks = scenario.get("checks") or {}
    for term in checks.get("required_output_terms", []):
        alternatives = term_alternatives(term)
        if len(alternatives) == 1 and re.fullmatch(r"[^\s_-]+", alternatives[0]):
            graders.append({
                "type": "output-contains",
                "config": {"substring": alternatives[0], "case_sensitive": False},
            })
        else:
            graders.append({
                "type": "output-matches",
                "config": {"pattern": output_term_pattern(term)},
            })
    if checks.get("tests_required"):
        graders.append({
            "type": "run-command",
            "config": {"command": checks.get("test_command", "python3 -m pytest -q")},
        })
    if not graders:
        graders.append({
            "type": "output-contains",
            "config": {"substring": "completed", "case_sensitive": False},
        })
    if scenario.get("rubric"):
        graders.append({
            "type": "prompt", "name": "rubric",
            "config": {"evidence": ["trajectory", "repo"]},
        })
    return graders


def generate_adapter_specs(
    scenarios: list[dict[str, Any]], agent: dict[str, Any],
    agent_version: str, suite_version: str,
) -> dict[str, Any]:
    version = f"agent-{agent_version}-suite-{suite_version}"
    candidate = agent_markdown(agent)
    vally_scenarios: list[dict[str, Any]] = []
    waza_scenarios: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        checks = scenario.get("checks") or {}
        rubric = [str(item) for item in scenario.get("rubric", [])]
        scenario_candidate = agent_markdown(
            agent, task_mode=str(scenario.get("task_mode") or "change")
        )
        vally_scenarios.append({
            "id": scenario_id,
            "path": f"{scenario_id}.eval.yaml",
            "fixture": _fixture(scenario),
            "spec": {
                "name": f"workbench-{scenario_id}",
                "version": version,
                "type": "capability",
                "defaults": {
                    "runs": 1, "timeout": "10m", "executor": "copilot-sdk",
                },
                "agent_environment": {"files": [
                    {"src": f"fixtures/{scenario_id}", "dest": "."},
                ]},
                "stimuli": [{
                    "name": scenario_id,
                    "prompt": render_prompt(
                        "vally-candidate-task",
                        candidate_profile=scenario_candidate,
                        scenario_prompt=str(scenario["prompt"]),
                    ),
                    "graders": _vally_graders(scenario),
                    "rubric": rubric,
                    "constraints": {"max_turns": 40, "max_duration": "10m"},
                }],
                "scoring": {"threshold": float(checks.get("minimum_score", 0.8))},
            },
        })
        waza_graders = [{
            "type": "file", "name": f"file-{path}",
            "config": {"must_exist": [path]},
        } for path in checks.get("required_files", [])]
        if not waza_graders:
            waza_graders.append({
                "type": "behavior", "name": "bounded-run",
                "config": {"max_tool_calls": 40, "max_duration_ms": 600000},
            })
        waza_scenarios.append({
            "id": scenario_id,
            "root": scenario_id,
            "agent_file": scenario_candidate,
            "fixture": _fixture(scenario),
            "task": {
                "id": scenario_id,
                "name": scenario.get("name", scenario_id),
                "description": scenario.get("description", scenario["prompt"]),
                "inputs": {
                    "prompt": scenario["prompt"],
                    "context": {"fixture": f"fixtures/{scenario_id}"},
                },
            },
            "spec": {
                "name": f"workbench-{scenario_id}",
                "skill": "candidate",
                "schemaVersion": "1.0",
                "version": version,
                "config": {
                    "trials_per_task": 1, "timeout_seconds": 600,
                    "executor": "copilot-sdk", "parallel": False,
                },
                "graders": waza_graders,
                "tasks": ["tasks/*.yaml"],
            },
        })
    bundle = {
        "schema_version": "1.0",
        "generated_for": {
            "agent_version": agent_version, "suite_version": suite_version,
        },
        "vally": {"agent_file": candidate, "scenarios": vally_scenarios},
        "waza": {"scenarios": waza_scenarios},
    }
    validate_adapter_specs(bundle, scenarios)
    return bundle


def _safe_relative(value: str, suffix: str | None = None) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value) and not path.is_absolute() and ".." not in path.parts
        and (suffix is None or value.endswith(suffix))
    )


def validate_adapter_specs(
    bundle: dict[str, Any], scenarios: list[dict[str, Any]],
) -> None:
    expected = [str(item.get("id", "")) for item in scenarios]
    if bundle.get("schema_version") != "1.0":
        raise ValueError("Adapter specs require schema_version 1.0")
    vally = bundle.get("vally") or {}
    waza = bundle.get("waza") or {}
    if not isinstance(vally.get("agent_file"), str):
        raise TypeError("Vally adapter specs require agent_file")
    for adapter, entries in (
        ("Vally", vally.get("scenarios")), ("Waza", waza.get("scenarios"))
    ):
        if not isinstance(entries, list):
            raise TypeError(
                f"{adapter} adapter specs require a scenarios list")
        ids = [str(item.get("id", ""))
               for item in entries if isinstance(item, dict)]
        if ids != expected:
            raise ValueError(
                f"{adapter} spec scenario ids must match dataset scenarios in order"
            )
    for item in vally["scenarios"]:
        if not _safe_relative(str(item.get("path", "")), ".eval.yaml"):
            raise ValueError(
                "Vally spec paths must be relative .eval.yaml files")
        if not isinstance(item.get("spec"), dict):
            raise TypeError("Every Vally scenario requires a spec object")
    for item in waza["scenarios"]:
        root = str(item.get("root", ""))
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", root):
            raise ValueError("Waza scenario roots must be safe slugs")
        if not all(isinstance(item.get(key), expected_type) for key, expected_type in (
            ("agent_file", str), ("fixture", dict), ("task", dict), ("spec", dict)
        )):
            raise ValueError(
                "Every Waza scenario requires agent, fixture, task, and spec")
