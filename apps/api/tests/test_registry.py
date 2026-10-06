from app import registry


def test_agent_yaml_cannot_self_promote(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
status: promoted
identity:
  id: did:local:candidate
capabilities: [repository.read]
"""

    saved = registry.save_definition("agents", "candidate", raw)

    assert saved["data"]["status"] == "draft"


def test_promotion_gate_can_mark_agent_promoted(tmp_path, monkeypatch):
    monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
    raw = """name: Candidate
version: 1.0.0
status: promoted
identity:
  id: did:local:candidate
capabilities: [repository.read]
"""

    saved = registry.save_definition(
        "agents", "candidate", raw, allow_agent_promotion=True
    )

    assert saved["data"]["status"] == "promoted"
