import asyncio
from datetime import UTC, datetime

from .decision import ModelRecoveryDecision
from .request import ModelRecoveryRequest


class ModelRecoveryBroker:
    def __init__(self) -> None:
        self._requests: dict[str, ModelRecoveryRequest] = {}

    def get(self, task_id: str) -> dict | None:
        request = self._requests.get(task_id)
        return request.public() if request and not request.future.done() else None

    async def request(
        self,
        *,
        task_id: str,
        provider: str,
        model: str,
        fallback_provider: str,
        fallback_model: str,
        error: str,
        attempts: int,
        timeout: int,
    ) -> ModelRecoveryDecision:
        previous = self._requests.pop(task_id, None)
        if previous and not previous.future.done():
            previous.future.set_result(ModelRecoveryDecision("cancel"))
        future = asyncio.get_running_loop().create_future()
        request = ModelRecoveryRequest(
            task_id=task_id,
            provider=provider,
            model=model,
            fallback_provider=fallback_provider,
            fallback_model=fallback_model,
            error=error[:2000],
            created_at=datetime.now(UTC),
            attempts=attempts,
            future=future,
        )
        self._requests[task_id] = request
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return ModelRecoveryDecision("fallback")
        finally:
            if self._requests.get(task_id) is request:
                self._requests.pop(task_id, None)

    def resolve(self, task_id: str, decision: ModelRecoveryDecision) -> bool:
        request = self._requests.get(task_id)
        if not request or request.future.done():
            return False
        request.future.set_result(decision)
        return True

    def cancel(self, task_id: str) -> None:
        self.resolve(task_id, ModelRecoveryDecision("cancel"))
