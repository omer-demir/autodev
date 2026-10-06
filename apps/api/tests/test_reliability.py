from app.reliability import ReliabilityBridge


def test_allowed_governance_event_keeps_reliability_healthy():
    bridge = ReliabilityBridge()

    bridge.observe_event("tool.allowed", {
        "task_id": "TASK-001",
        "capability": "repository.read",
        "decision": "ALLOW",
        "policy": "development-v1",
    })

    status = bridge.status()
    assert status["slo"]["status"] == "healthy"
    assert status["agent_os"]["blocked_count"] == 0
    assert status["incidents"]["open_incidents"] == 0


def test_denied_governance_event_opens_incident_and_exhausts_budget():
    bridge = ReliabilityBridge()

    bridge.observe_event("tool.denied", {
        "task_id": "TASK-001",
        "capability": "host.credentials.read",
        "decision": "DENY",
        "policy": "development-v1",
    })

    status = bridge.status()
    assert status["slo"]["status"] == "exhausted"
    assert status["agent_os"]["blocked_count"] == 1
    assert status["incidents"]["open_incidents"] == 1
    assert status["open_incidents"][0]["severity"] == "p1"
