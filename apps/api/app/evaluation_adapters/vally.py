import json
import copy
import shutil
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


class VallyAdapter(EvaluationAdapter):
    name = "vally"

    async def run(
        self,
        *,
        dataset: dict[str, Any],
        agent: dict[str, Any],
        model_provider: str,
        model_name: str,
        output_dir: Path,
    ) -> AdapterResult:
        executable = shutil.which("vally")
        if not executable:
            raise RuntimeError(
                "Vally CLI is not installed; install @microsoft/vally-cli")
        root = output_dir / self.name
        root.mkdir(parents=True, exist_ok=True)
        bundle = adapter_bundle(dataset, agent)
        vally = bundle["vally"]
        agent_file = root / "candidate.agent.md"
        agent_file.write_text(vally["agent_file"], encoding="utf-8")
        provider = model_provider.casefold()
        if provider not in {"copilot", "ollama"}:
            raise ValueError(
                f"Unsupported Vally evaluator provider: {provider}")
        provider_config = None
        environment = None
        if provider == "ollama":
            provider_config = {
                "type": "openai",
                "baseUrl": openai_provider_url(get_settings().ollama_url),
            }
        else:
            environment = {
                "EVALUATE_USE_HOST_COPILOT_HOME": "1",
                "COPILOT_HOME": str(
                    Path(get_settings().copilot_home).expanduser().resolve()
                ),
            }
        specs: list[Path] = []
        for item in adapter_scenarios(bundle, "vally"):
            scenario_id = str(item["id"])
            _write_fixture(root, item.get("fixture") or {}, scenario_id)
            spec = copy.deepcopy(item["spec"])
            defaults = spec.setdefault("defaults", {})
            defaults["executor"] = (
                {"name": "copilot-sdk", "config": {"provider": provider_config}}
                if provider_config else "copilot-sdk"
            )
            if model_name not in {"", "auto"}:
                defaults["model"] = model_name
                if any(
                    grader.get("type") in {"prompt", "panel"}
                    for stimulus in spec.get("stimuli", [])
                    for grader in stimulus.get("graders", [])
                ):
                    defaults["judge_model"] = model_name
            if defaults.get("judge_model") and provider_config:
                defaults["judge_provider"] = provider_config
            path = root / str(item["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(
                spec, sort_keys=False), encoding="utf-8")
            specs.append(path)
        results_root = root / "results"
        arguments = [executable, "eval"]
        for spec in specs:
            arguments.extend(["--eval-spec", str(spec)])
        arguments.extend([
            "--output-dir", str(results_root), "--output", "jsonl",
            "--require-pass", "--workers", "1",
        ])
        # Each trial-result JSONL record embeds a full trajectory (~100 KB).
        code, output, duration = await command(
            arguments, root, environment=environment,
            max_output_chars=50_000_000,
        )
        (root / "console.log").write_text(output, encoding="utf-8")
        records: list[dict[str, Any]] = []
        for line in output.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        normalized: list[dict[str, Any]] = []
        scores: list[float] = []
        for item in records:
            if item.get("type") != "trial-result":
                continue
            grade = item.get("gradeResult")
            if not isinstance(grade, dict):
                continue
            raw_score = grade.get("score")
            if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
                continue
            score_value = min(1.0, max(0.0, float(raw_score)))
            stimulus = item.get("stimulus")
            scenario_id = (
                str(stimulus.get("name") or stimulus.get("id") or "")
                if isinstance(stimulus, dict)
                else str(stimulus or "")
            )
            details = grade.get("details")
            details = details if isinstance(details, list) else []
            failed_graders = [
                str(detail.get("evidence") or detail.get(
                    "name") or "grader failed")
                for detail in details
                if isinstance(detail, dict) and detail.get("passed") is False
            ]
            normalized.append({
                **item,
                "scenario_id": scenario_id,
                "name": scenario_id,
                "passed": grade.get("passed") is True,
                "score": round(score_value, 4),
                "judge": {
                    "reason": "; ".join(failed_graders)
                    or str(grade.get("evidence") or ""),
                    "details": details,
                },
            })
            scores.append(score_value)
        score = sum(scores) / len(scores) if scores else float(code == 0)
        return AdapterResult(
            self.name, code == 0, round(score, 4), round(
                duration, 3), normalized,
            {"exit_code": code, "records": len(records),
             "scenarios": len(normalized),
             "latency_seconds": round(duration, 3),
             "parsed_scores": len(scores),
             "executor_provider": provider,
             "console_log": "vally/console.log"}, str(
                root), version(executable),
            None if code == 0 or len(normalized) >= len(
                specs) else output[-4000:],
        )
