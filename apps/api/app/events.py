import asyncio
import json
import logging

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .config import get_settings
from .observability import observe_event_stream


logger = logging.getLogger("autodev.events")


class EventHub:
    def __init__(self) -> None:
        self.connections: dict[WebSocket, tuple[str | None, str]] = {}
        self._readers: dict[WebSocket, asyncio.Task[None]] = {}
        settings = get_settings()
        self._stream = settings.event_stream_name
        self._max_length = settings.event_stream_max_length
        self._redis = Redis.from_url(
            settings.redis_url) if settings.redis_url else None

    async def connect(
        self,
        websocket: WebSocket,
        organization_id: str,
        task_id: str | None = None,
        cursor: str | None = None,
    ) -> None:
        await websocket.accept()
        self.connections[websocket] = (task_id, organization_id)
        if self._redis:
            self._readers[websocket] = asyncio.create_task(
                self._read_stream(websocket, cursor or "$")
            )

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.pop(websocket, None)
        reader = self._readers.pop(websocket, None)
        if reader:
            reader.cancel()

    async def _read_stream(self, websocket: WebSocket, cursor: str) -> None:
        assert self._redis is not None
        current = cursor
        try:
            while websocket in self.connections:
                values = await self._redis.xread(
                    {self._stream: current}, block=1000, count=100
                )
                for _, entries in values:
                    for stream_id, fields in entries:
                        current = (
                            stream_id.decode()
                            if isinstance(stream_id, bytes)
                            else str(stream_id)
                        )
                        raw = fields.get(b"payload") or fields.get("payload")
                        if not raw:
                            continue
                        payload = json.loads(raw)
                        task_id, organization_id = self.connections[websocket]
                        if payload.get("organization_id") != organization_id:
                            continue
                        if task_id is not None and payload.get("task_id") != task_id:
                            continue
                        await websocket.send_json({**payload, "cursor": current})
                        observe_event_stream(operation="delivered")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Redis event reader stopped")
            self.disconnect(websocket)

    async def publish(self, payload: dict) -> None:
        if self._redis:
            try:
                await self._redis.xadd(
                    self._stream,
                    {"payload": json.dumps(payload, default=str)},
                    maxlen=self._max_length,
                    approximate=True,
                )
                observe_event_stream(operation="published")
                return
            except RedisError:
                observe_event_stream(operation="publish_failed")
                logger.exception(
                    "Redis event publish failed; using local fan-out")
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

    async def close(self) -> None:
        for connection in list(self.connections):
            self.disconnect(connection)
        if self._redis:
            await self._redis.aclose()


event_hub = EventHub()
