import json
from pathlib import Path
from typing import Any

from .config import get_settings


class EvidenceProvider:
    def __init__(self) -> None:
        self.root = Path(get_settings().evidence_dir)

    def write(self, task_id: str, name: str, content: Any) -> None:
        directory = self.root / task_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{name}.json").write_text(
            json.dumps(content, indent=2, default=str), encoding="utf-8"
        )

    def bundle(self, task_id: str) -> dict[str, Any]:
        directory = self.root / task_id
        if not directory.exists():
            return {}
        return {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        }


evidence_provider = EvidenceProvider()
