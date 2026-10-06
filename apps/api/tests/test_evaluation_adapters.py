import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.evaluation_adapters import VallyAdapter, WazaAdapter


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


@pytest.mark.asyncio
async def test_vally_adapter_renders_current_spec(tmp_path: Path):
    with patch("app.evaluation_adapters.shutil.which", return_value="/usr/bin/vally"), patch(
        "app.evaluation_adapters._command", new=AsyncMock(return_value=(0, '{"score":1}\n', 1.0))
    ), patch("app.evaluation_adapters._version", return_value="0.17.0"):
        result = await VallyAdapter().run(
            dataset=DATASET, agent=AGENT, model_name="auto", output_dir=tmp_path
        )

    spec = yaml.safe_load(
        (tmp_path / "vally" / "writes-report.eval.yaml").read_text())
    assert spec["defaults"] == {"runs": 1,
                                "timeout": "10m", "executor": "copilot-sdk"}
    assert spec["agent_environment"]["files"][1]["dest"] == ".github/agents/candidate.agent.md"
    assert [grader["type"] for grader in spec["stimuli"][0]["graders"]] == [
        "file-exists", "run-command"
    ]
    assert result.passed is True


@pytest.mark.asyncio
async def test_waza_adapter_renders_current_spec(tmp_path: Path):
    async def fake_command(arguments, cwd, timeout=1800):
        output_index = arguments.index("--output") + 1
        Path(arguments[output_index]).write_text(
            json.dumps({"overall_score": 1.0}))
        return 0, "passed", 1.0

    with patch("app.evaluation_adapters.shutil.which", return_value="/usr/bin/waza"), patch(
        "app.evaluation_adapters._command", new=fake_command
    ), patch("app.evaluation_adapters._version", return_value="0.38.8"):
        result = await WazaAdapter().run(
            dataset=DATASET, agent=AGENT, model_name="auto", output_dir=tmp_path
        )

    root = tmp_path / "waza" / "writes-report"
    spec = yaml.safe_load((root / "eval.yaml").read_text())
    task = yaml.safe_load((root / "tasks" / "task.yaml").read_text())
    assert spec["schemaVersion"] == "1.0"
    assert spec["config"] == {
        "trials_per_task": 1,
        "timeout_seconds": 600,
        "executor": "copilot-sdk",
        "parallel": False,
    }
    assert spec["graders"][0]["config"] == {
        "must_exist": ["evaluation/report.md"]}
    assert task["inputs"]["files"] == [{"path": "README.md"}]
    assert result.passed is True
