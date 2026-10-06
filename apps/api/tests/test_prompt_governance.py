from app.prompt_governance import evaluate_agent_prompt
from app.registry import get_definition


def test_developer_prompt_meets_promotion_defense_gate():
    definition = get_definition("agents", "developer")["data"]

    evidence = evaluate_agent_prompt("developer", definition)

    assert evidence["grade"] == "B"
    assert evidence["min_grade"] == "C"
    assert evidence["blocking"] is False
    assert evidence["defended"] == 15
    assert evidence["total"] == 17
    assert len(evidence["prompt_hash"]) == 64
