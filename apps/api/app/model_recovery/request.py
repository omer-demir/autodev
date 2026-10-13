import asyncio
from dataclasses import dataclass
from datetime import datetime

from .decision import ModelRecoveryDecision


@dataclass
class ModelRecoveryRequest:
    task_id: str
    provider: str
    model: str
    fallback_provider: str
    fallback_model: str
    error: str
    created_at: datetime
    attempts: int
    future: asyncio.Future[ModelRecoveryDecision]

    def public(self) -> dict:
        return {
            "task_id": self.task_id,
            "provider": self.provider,
            "model": self.model,
            "fallback_provider": self.fallback_provider,
            "fallback_model": self.fallback_model,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "attempts": self.attempts,
        }
