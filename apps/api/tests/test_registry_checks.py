import json
import subprocess

from app.registry_checks import check_skill_with_waza


def test_waza_check_uses_structured_readiness_not_exit_code(monkeypatch):
    report = {
        "skills": [{
            "ready": False,
            "compliance": {
                "issues": [{"message": "Description is too short"}],
            },
            "eval": {"found": False},
        }],
    }
    monkeypatch.setattr("app.registry_checks.shutil.which",
                        lambda name: "/usr/bin/waza")
    monkeypatch.setattr(
        "app.registry_checks.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=json.dumps(report), stderr=""
        ),
    )

    result = check_skill_with_waza("review", {
        "name": "review",
        "description": "Review repository changes.",
        "instructions": "Inspect the diff and report concrete findings.",
    })

    assert result["check"] == "waza-check"
    assert result["valid"] is False
    assert result["checker"]["exit_code"] == 0
    assert "Description is too short" in result["detail"]
    assert "evaluation suite is missing" in result["detail"]


def test_missing_waza_reports_native_checker_provenance(monkeypatch):
    monkeypatch.setattr("app.registry_checks.shutil.which", lambda name: None)

    result = check_skill_with_waza("review", {
        "name": "review",
        "description": "Review repository changes.",
        "instructions": "Inspect the diff and report concrete findings.",
    })

    assert result["valid"] is True
    assert result["check"] == "native-schema"
    assert result["checker"] == {"name": "waza", "available": False}
