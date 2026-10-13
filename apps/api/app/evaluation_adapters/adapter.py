from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .result import AdapterResult


class EvaluationAdapter(ABC):
    """External evaluator boundary with normalized, evidence-linked results."""

    name: str

    @abstractmethod
    async def run(
        self,
        *,
        dataset: dict[str, Any],
        agent: dict[str, Any],
        model_provider: str,
        model_name: str,
        output_dir: Path,
    ) -> AdapterResult: ...
