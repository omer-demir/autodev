import pytest

from app.events import EventHub


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_task_subscription_receives_only_matching_events():
    hub = EventHub()
    global_socket = FakeWebSocket()
    task_socket = FakeWebSocket()
    other_task_socket = FakeWebSocket()
    other_org_socket = FakeWebSocket()

    await hub.connect(global_socket, "org-1")  # type: ignore[arg-type]
    # type: ignore[arg-type]
    await hub.connect(task_socket, "org-1", "TASK-001")
    # type: ignore[arg-type]
    await hub.connect(other_task_socket, "org-1", "TASK-002")
    await hub.connect(other_org_socket, "org-2")  # type: ignore[arg-type]
    payload = {
        "event": "task.updated", "task_id": "TASK-001", "organization_id": "org-1"
    }
    await hub.publish(payload)

    assert global_socket.messages == [payload]
    assert task_socket.messages == [payload]
    assert other_task_socket.messages == []
    assert other_org_socket.messages == []
