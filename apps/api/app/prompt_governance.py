from typing import Any

from agent_compliance.prompt_defense import PromptDefenseConfig, PromptDefenseEvaluator

from .config import get_settings
from .prompts import render_agent_system_prompt
from .registry import get_definition

_GRADES = {"A", "B", "C", "D", "F"}


def evaluate_agent_prompt(agent_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    min_grade = settings.prompt_defense_min_grade.strip().upper()
    if min_grade not in _GRADES:
        raise ValueError(
            "WORKBENCH_PROMPT_DEFENSE_MIN_GRADE must be one of A, B, C, D, or F"
        )
    policy = get_definition(
        "policies", str(definition.get("policy", "development"))
    )["data"]
    policy_runtime = policy.get("runtime", {})
    max_tool_calls = max(
        1, int(policy_runtime.get("max_tool_calls", settings.max_agent_steps))
    )
    max_shell_calls = max(
        1, int(policy_runtime.get("max_shell_calls", max_tool_calls))
    )
    prompt = render_agent_system_prompt(
        definition,
        agent_id=agent_id,
        task_mode="change",
        max_tool_calls=max_tool_calls,
        max_shell_calls=max_shell_calls,
    )
    evaluator = PromptDefenseEvaluator(
        PromptDefenseConfig(min_grade=min_grade))
    report = evaluator.evaluate(prompt)
    return {
        "min_grade": min_grade,
        "grade": report.grade,
        "score": report.score,
        "coverage": report.coverage,
        "defended": report.defended,
        "total": report.total,
        "missing_vectors": report.missing,
        "prompt_hash": report.prompt_hash,
        "blocking": report.is_blocking(min_grade),
    }
