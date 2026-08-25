"""Persistence interfaces with a local implementation for development."""

import json
from pathlib import Path
from typing import Protocol

from .models import ProcessingAudit


class AuditStore(Protocol):
    def seen(self, sha256: str) -> bool: ...
    def save(self, audit: ProcessingAudit, records: list[dict[str, object]]) -> None: ...


class LocalAuditStore:
    """Append-only JSONL store that makes local runs inspectable."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def seen(self, sha256: str) -> bool:
        if not self.path.exists():
            return False
        return any(
            json.loads(line).get("sha256") == sha256 for line in self.path.read_text().splitlines()
        )

    def save(self, audit: ProcessingAudit, records: list[dict[str, object]]) -> None:
        payload = audit.model_dump(mode="json") | {"relationships": records}
        with self.path.open("a") as handle:
            handle.write(json.dumps(payload) + "\n")
