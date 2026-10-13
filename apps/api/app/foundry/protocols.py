from collections.abc import Awaitable, Callable
from typing import Any, Protocol

EventCallback = Callable[
    [str, str, str, str, dict[str, Any] | None], Awaitable[None]
]
SteeringProvider = Callable[[], Awaitable[list[str]]]


class ToolExecutor(Protocol):
    async def execute(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]: ...
