import json
import copy
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from ..config import get_settings
from .adapter import EvaluationAdapter
from .bundle import adapter_bundle, adapter_scenarios
from .result import AdapterResult
from .support import (
    command,
    openai_provider_url,
    version,
)


def _write_fixture(root: Path, fixture: dict[str, Any], scenario_id: str) -> Path:
    target_root = root / "fixtures" / scenario_id
    for relative, content in (fixture.get("files") or {}).items():
        target = (target_root / str(relative)).resolve()
        if target_root.resolve() not in target.parents:
            raise ValueError(f"Fixture path escapes its root: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    return target_root


class WazaAdapter(EvaluationAdapter):
    name = "waza"

    async def run(
        self,
        *,
        dataset: dict[str, Any],
        agent: dict[str, Any],
        model_provider: str,
        model_name: str,
        output_dir: Path,
    ) -> AdapterResult:
        executable = shutil.which("waza")
        if not executable:
            raise RuntimeError(
                "Waza CLI is not installed; install the Microsoft Waza binary")
        root = output_dir / self.name
        root.mkdir(parents=True, exist_ok=True)
        bundle = adapter_bundle(dataset, agent)
        provider = model_provider.casefold()
        if provider not in {"copilot", "ollama"}:
            raise ValueError(
                f"Unsupported Waza evaluator provider: {provider}")
        environment = None
        if provider == "ollama":
            environment = {
                "COPILOT_PROVIDER_BASE_URL": openai_provider_url(
                    get_settings().ollama_url
                ),
                "COPILOT_PROVIDER_TYPE": "openai",
                "COPILOT_PROVIDER_WIRE_API": "completions",
            }
        else:
            environment = {
                "COPILOT_HOME": str(
                    Path(get_settings().copilot_home).expanduser().resolve()
                ),
            }
        normalized: list[dict[str, Any]] = []
        started = time.monotonic()
        all_passed = True
        for item in adapter_scenarios(bundle, "waza"):
            scenario_id = str(item["id"])
            scenario_root = root / str(item["root"])
            scenario_root.mkdir(parents=True, exist_ok=True)
            (scenario_root / "candidate.agent.md").write_text(
                item["agent_file"], encoding="utf-8"
            )
            fixture = _write_fixture(
                scenario_root, item.get("fixture") or {}, scenario_id
            )
            task_dir = scenario_root / "tasks"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "task.yaml").write_text(
                yaml.safe_dump(item["task"], sort_keys=False), encoding="utf-8"
            )
            spec = copy.deepcopy(item["spec"])
            config = spec.setdefault("config", {})
            if model_name not in {"", "auto"}:
                config["model"] = model_name
            spec_path = scenario_root / "eval.yaml"
            spec_path.write_text(yaml.safe_dump(
                spec, sort_keys=False), encoding="utf-8")
            result_path = scenario_root / "results.json"
            code, output, scenario_duration = await command(
                [executable, "run", str(spec_path), "--context-dir", str(fixture),
                 "--output", str(result_path), "--no-cache"],
                scenario_root,
                environment=environment,
            )
            (scenario_root / "console.log").write_text(output, encoding="utf-8")
            parsed: dict[str, Any] = {}
            if result_path.exists():
                try:
                    parsed = json.loads(
                        result_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    parsed = {}
            summary = parsed.get("summary")
            summary = summary if isinstance(summary, dict) else {}
            raw_score = next((
                value for value in (
                    summary.get("aggregate_score"),
                    summary.get("weighted_score"),
                    summary.get("success_rate"),
                    parsed.get("overall_score"),
                    parsed.get("avg_score"),
                    parsed.get("score"),
                )
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            ), float(code == 0))
            scenario_score = min(1.0, max(0.0, float(raw_score)))
            normalized.append({
                "scenario_id": scenario_id, "passed": code == 0,
                "score": round(scenario_score, 4),
                "exit_code": code, "result": parsed,
                "duration_seconds": round(scenario_duration, 3),
                "console_log": f"waza/{item['root']}/console.log",
                "result_file": f"waza/{item['root']}/results.json",
                "error": None if code == 0 else output[-4000:],
            })
            all_passed = all_passed and code == 0
        score = sum(
            float(item["score"]) for item in normalized
        ) / max(1, len(normalized))
        duration = time.monotonic() - started
        return AdapterResult(
            self.name, all_passed, round(
                score, 4), round(duration, 3), normalized,
            {"scenarios": len(normalized),
             "passed_scenarios": sum(item["passed"] for item in normalized),
             "failed_scenarios": sum(not item["passed"] for item in normalized),
             "latency_seconds": round(duration, 3),
             "exit_codes": [item["exit_code"] for item in normalized],
             "executor_provider": provider},
            str(root), version(executable),
            None if all_passed else "\n\n".join(
                f"{item['scenario_id']}: {item['error']}"
                for item in normalized if item["error"]
            )[-4000:],
        )
