import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml


def check_skill_with_waza(identifier: str, data: dict[str, Any]) -> dict[str, Any]:
    executable = shutil.which("waza")
    if not executable:
        return {
            "valid": True,
            "check": "native-schema",
            "detail": (
                "Skill passes native schema validation. Waza is not installed, "
                "so no external skill checker ran."
            ),
            "checker": {"name": "waza", "available": False},
        }

    frontmatter = yaml.safe_dump(
        {
            "name": str(data["name"]),
            "description": str(data["description"]),
        },
        sort_keys=False,
    ).strip()
    content = f"---\n{frontmatter}\n---\n\n{data['instructions'].strip()}\n"
    try:
        with tempfile.TemporaryDirectory(prefix="autodev-waza-") as directory:
            skill_directory = Path(directory) / identifier
            skill_directory.mkdir()
            (skill_directory / "SKILL.md").write_text(content, encoding="utf-8")
            completed = subprocess.run(
                [
                    executable,
                    "check",
                    str(skill_directory),
                    "--format",
                    "json",
                    "--no-update-check",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return {
            "valid": False,
            "check": "waza-check",
            "detail": "Waza skill validation timed out after 30 seconds.",
            "checker": {"name": "waza", "available": True, "timed_out": True},
        }

    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        report: Any = json.loads(output)
    except json.JSONDecodeError:
        report = {"output": output}
    skill_reports = report.get(
        "skills", []) if isinstance(report, dict) else []
    passed = (
        completed.returncode == 0
        and bool(skill_reports)
        and all(item.get("ready") is True for item in skill_reports)
    )
    issues = [
        str(issue.get("message"))
        for item in skill_reports
        for issue in item.get("compliance", {}).get("issues", [])
        if issue.get("message")
    ]
    if any(item.get("eval", {}).get("found") is False for item in skill_reports):
        issues.append("evaluation suite is missing")
    return {
        "valid": passed,
        "check": "waza-check",
        "detail": (
            "Waza check passed for the materialized native skill."
            if passed
            else "Waza check found submission-readiness issues: "
            + "; ".join(issues[:3] or ["see the structured Waza report"])
        ),
        "checker": {
            "name": "waza",
            "available": True,
            "exit_code": completed.returncode,
            "input_format": "materialized-skill-md",
        },
        "report": report,
    }
