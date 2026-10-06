from fastapi import WebSocket


class EventHub:
    def __init__(self) -> None:
        self.connections: dict[WebSocket, tuple[str | None, str]] = {}

    async def connect(
        self, websocket: WebSocket, organization_id: str, task_id: str | None = None
    ) -> None:
        await websocket.accept()
        self.connections[websocket] = (task_id, organization_id)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.pop(websocket, None)

    async def publish(self, payload: dict) -> None:
        stale: list[WebSocket] = []
        for connection, (task_id, organization_id) in list(self.connections.items()):
            if payload.get("organization_id") != organization_id:
                continue
            if task_id is not None and payload.get("task_id") != task_id:
                continue
            try:
                await connection.send_json(payload)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)


event_hub = EventHub()
