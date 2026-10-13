from abc import ABC, abstractmethod
from typing import Any


class SandboxProvider(ABC):
    @abstractmethod
    async def readiness(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def create(self, project: dict[str, Any]) -> dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, session_id: str, command: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def execute_args(
        self,
        session_id: str,
        arguments: list[str],
        *,
        network_access: bool = False,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def kill(self, session_id: str) -> None:
        pass
