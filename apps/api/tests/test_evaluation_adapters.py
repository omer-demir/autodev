import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.evaluation_adapters import VallyAdapter, WazaAdapter
from app.evaluation_adapters.bundle import adapter_bundle, adapter_scenarios
from app.evaluation_adapters.support import command, version
from app.evaluation_adapters.specs import generate_adapter_specs


DATASET = {
    "content_hash": "a" * 64,
    "scenarios": [{
        "id": "writes-report",
        "name": "Writes report",
        "description": "Create an evidence report.",
        "prompt": "Inspect the fixture and write evaluation/report.md.",
        "fixture": {"files": {"README.md": "# Fixture\n"}},
        "checks": {
            "required_files": ["evaluation/report.md"],
            "required_output_terms": ["verified evidence"],
            "tests_required": True,
            "test_command": "python3 -m pytest -q",
            "minimum_score": 0.8,
        },
        "rubric": ["Use repository-specific evidence."],
    }],
}
AGENT = {
    "description": "Implement and test repository changes.",
    "capabilities": ["repository.read", "repository.write", "test.run"],
    "deny": ["host.credentials.read"],
}
DATASET["adapter_specs"] = generate_adapter_specs(
    DATASET["scenarios"], AGENT, "1.2.3", "1.0.0"
)


def test_canonical_adapter_bundle_exposes_nested_scenarios():
    bundle = adapter_bundle(DATASET, AGENT)

    assert [item["id"] for item in adapter_scenarios(bundle, "vally")] == [
        "writes-report"
    ]
    assert [item["id"] for item in adapter_scenarios(bundle, "waza")] == [
        "writes-report"
    ]


def test_adapter_bundle_rejects_partial_dataset_with_actionable_error():
    with pytest.raises(
        TypeError, match="full dataset record must be passed"
    ):
        adapter_bundle({"adapter_specs": DATASET["adapter_specs"]}, AGENT)


def test_evaluator_version_extracts_semantic_version():
    with patch("app.evaluation_adapters.support.subprocess.run") as run:
        run.return_value = SimpleNamespace(
            stdout="waza version 0.38.10\n", stderr=""
        )
        assert version("/usr/bin/waza") == "0.38.10"


@pytest.mark.asyncio
async def test_command_kills_subprocess_when_cancelled(tmp_path: Path):
    communicate_started = asyncio.Event()

    class Process:
        returncode = None
        pid = 123
        killed = False

        async def communicate(self):
            communicate_started.set()
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.returncode = -9
            return self.returncode

    process = Process()
    with patch(
        "app.evaluation_adapters.support.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ), patch("app.evaluation_adapters.support.os.name", "nt"):
        task = asyncio.create_task(command(["evaluator"], tmp_path))
        await communicate_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert process.killed is True


@pytest.mark.asyncio
async def test_vally_adapter_renders_current_spec(tmp_path: Path):
    dataset = {
        **DATASET, "adapter_specs": json.loads(json.dumps(DATASET["adapter_specs"]))}
    dataset["adapter_specs"]["vally"]["scenarios"][0]["spec"]["scoring"]["threshold"] = 0.93
    with patch("app.evaluation_adapters.vally.shutil.which", return_value="/usr/bin/vally"), patch(
        "app.evaluation_adapters.vally.command", new=AsyncMock(return_value=(0, '{"score":1}\n', 1.0))
    ), patch("app.evaluation_adapters.vally.version", return_value="0.17.0"), patch(
        "app.evaluation_adapters.vally.get_settings",
        return_value=SimpleNamespace(
            ollama_url="http://127.0.0.1:11434", copilot_home="~/.copilot"
        ),
    ):
        result = await VallyAdapter().run(
            dataset=dataset, agent=AGENT, model_provider="ollama",
            model_name="gemma4:e2b", output_dir=tmp_path,
        )

    spec = yaml.safe_load(
        (tmp_path / "vally" / "writes-report.eval.yaml").read_text())
    assert spec["type"] == "capability"
    assert spec["scoring"]["threshold"] == 0.93
    assert spec["defaults"] == {
        "runs": 1,
        "timeout": "10m",
        "executor": {
            "name": "copilot-sdk",
            "config": {"provider": {
                "type": "openai", "baseUrl": "http://127.0.0.1:11434/v1",
            }},
        },
        "model": "gemma4:e2b",
        "judge_model": "gemma4:e2b",
        "judge_provider": {
            "type": "openai", "baseUrl": "http://127.0.0.1:11434/v1",
        },
    }
    assert spec["agent_environment"]["files"] == [{
        "src": "fixtures/writes-report", "dest": ".",
    }]
    prompt = spec["stimuli"][0]["prompt"]
    assert "Act as the candidate defined below" in prompt
    assert "Do not delegate to another agent" in prompt
    assert "Implement and test repository changes." in prompt
    assert "You are a governed SDLC agent" in prompt
    assert "`search_text`" not in prompt
    assert "Never request `host.credentials.read`" in prompt
    assert "Inspect the fixture and write evaluation/report.md." in prompt
    assert [grader["type"] for grader in spec["stimuli"][0]["graders"]] == [
        "file-exists", "output-matches", "run-command", "prompt"
    ]
    assert result.passed is True
    assert result.metrics["executor_provider"] == "ollama"


@pytest.mark.asyncio
async def test_vally_adapter_reuses_configured_copilot_login(tmp_path: Path):
    async def fake_command(
        arguments, cwd, timeout=1800, environment=None, max_output_chars=200_000
    ):
        assert environment == {
            "EVALUATE_USE_HOST_COPILOT_HOME": "1",
            "COPILOT_HOME": str(tmp_path / "copilot-home"),
        }
        return 0, '{"score":1}\n', 1.0

    with patch("app.evaluation_adapters.vally.shutil.which", return_value="/usr/bin/vally"), patch(
        "app.evaluation_adapters.vally.command", new=fake_command
    ), patch("app.evaluation_adapters.vally.version", return_value="0.17.0"), patch(
        "app.evaluation_adapters.vally.get_settings",
        return_value=SimpleNamespace(
            ollama_url="http://127.0.0.1:11434",
            copilot_home=str(tmp_path / "copilot-home"),
        ),
    ):
        result = await VallyAdapter().run(
            dataset=DATASET, agent=AGENT, model_provider="copilot",
            model_name="gpt-5.6-luna", output_dir=tmp_path,
        )

    assert result.passed is True


@pytest.mark.asyncio
async def test_vally_adapter_scores_only_scenario_results(tmp_path: Path):
    output = "\n".join([
        json.dumps({
            "type": "trial-result",
            "stimulus": "first-scenario",
            "gradeResult": {
                "passed": True,
                "score": 0.875,
                "details": [{"score": 1}, {"metadata": {"score": 5}}],
            },
        }),
        json.dumps({
            "type": "trial-result",
            "stimulus": "second-scenario",
            "gradeResult": {
                "passed": False,
                "score": 0.6875,
                "details": [
                    {
                        "name": "required term",
                        "passed": False,
                        "score": 0,
                        "evidence": "Required term was not found",
                    },
                    {"metadata": {"score": 5}},
                ],
            },
        }),
        json.dumps({
            "type": "run-summary",
            "passed": False,
            "evals": [{"overallScore": 0.875}, {"overallScore": 0.6875}],
        }),
    ])
    with patch("app.evaluation_adapters.vally.shutil.which", return_value="/usr/bin/vally"), patch(
        "app.evaluation_adapters.vally.command",
        new=AsyncMock(return_value=(1, output, 1.0)),
    ), patch("app.evaluation_adapters.vally.version", return_value="0.17.0"), patch(
        "app.evaluation_adapters.vally.get_settings",
        return_value=SimpleNamespace(
            ollama_url="http://127.0.0.1:11434", copilot_home="~/.copilot"
        ),
    ):
        result = await VallyAdapter().run(
            dataset=DATASET, agent=AGENT, model_provider="copilot",
            model_name="gpt-5.6-luna", output_dir=tmp_path,
        )

    assert result.passed is False
    assert result.score == 0.7812
    assert result.metrics["records"] == 3
    assert result.metrics["scenarios"] == 2
    assert result.metrics["parsed_scores"] == 2
    assert [(item["scenario_id"], item["score"], item["passed"])
            for item in result.results] == [
        ("first-scenario", 0.875, True),
        ("second-scenario", 0.6875, False),
    ]
    assert result.results[1]["judge"]["reason"] == "Required term was not found"


@pytest.mark.asyncio
async def test_waza_adapter_reuses_configured_copilot_login(tmp_path: Path):
    async def fake_command(arguments, cwd, timeout=1800, environment=None):
        assert environment == {
            "COPILOT_HOME": str(tmp_path / "copilot-home"),
        }
        output_index = arguments.index("--output") + 1
        Path(arguments[output_index]).write_text(
            json.dumps({"overall_score": 1.0})
        )
        return 0, "passed", 1.0

    with patch("app.evaluation_adapters.waza.shutil.which", return_value="/usr/bin/waza"), patch(
        "app.evaluation_adapters.waza.command", new=fake_command
    ), patch("app.evaluation_adapters.waza.version", return_value="0.38.10"), patch(
        "app.evaluation_adapters.waza.get_settings",
        return_value=SimpleNamespace(
            ollama_url="http://127.0.0.1:11434",
            copilot_home=str(tmp_path / "copilot-home"),
        ),
    ):
        result = await WazaAdapter().run(
            dataset=DATASET, agent=AGENT, model_provider="copilot",
            model_name="gpt-5.6-luna", output_dir=tmp_path,
        )

    assert result.passed is True
    assert result.score == 1.0
    assert result.results[0]["score"] == 1.0


@pytest.mark.asyncio
async def test_waza_adapter_renders_current_spec(tmp_path: Path):
    dataset = {
        **DATASET, "adapter_specs": json.loads(json.dumps(DATASET["adapter_specs"]))}
    dataset["adapter_specs"]["waza"]["scenarios"][0]["spec"]["config"]["timeout_seconds"] = 321

    async def fake_command(arguments, cwd, timeout=1800, environment=None):
        assert environment == {
            "COPILOT_PROVIDER_BASE_URL": "http://127.0.0.1:11434/v1",
            "COPILOT_PROVIDER_TYPE": "openai",
            "COPILOT_PROVIDER_WIRE_API": "completions",
        }
        output_index = arguments.index("--output") + 1
        Path(arguments[output_index]).write_text(
            json.dumps({"overall_score": 1.0}))
        return 0, "passed", 1.0

    with patch("app.evaluation_adapters.waza.shutil.which", return_value="/usr/bin/waza"), patch(
        "app.evaluation_adapters.waza.command", new=fake_command
    ), patch("app.evaluation_adapters.waza.version", return_value="0.38.8"), patch(
        "app.evaluation_adapters.waza.get_settings",
        return_value=SimpleNamespace(
            ollama_url="http://127.0.0.1:11434", copilot_home="~/.copilot"
        ),
    ):
        result = await WazaAdapter().run(
            dataset=dataset, agent=AGENT, model_provider="ollama",
            model_name="gemma4:e2b", output_dir=tmp_path,
        )

    root = tmp_path / "waza" / "writes-report"
    spec = yaml.safe_load((root / "eval.yaml").read_text())
    task = yaml.safe_load((root / "tasks" / "task.yaml").read_text())
    assert spec["schemaVersion"] == "1.0"
    assert spec["config"] == {
        "trials_per_task": 1,
        "timeout_seconds": 321,
        "executor": "copilot-sdk",
        "parallel": False,
        "model": "gemma4:e2b",
    }
    assert spec["graders"][0]["config"] == {
        "must_exist": ["evaluation/report.md"]}
    assert task["inputs"]["context"]["fixture"] == "fixtures/writes-report"
    agent_text = (root / "candidate.agent.md").read_text()
    assert "tools:" in agent_text
    assert "- edit" in agent_text
    assert "- read" in agent_text
    assert result.passed is True
    assert result.metrics["executor_provider"] == "ollama"
