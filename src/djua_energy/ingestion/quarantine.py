"""In-memory quarantine for invalid telemetry records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class QuarantineEntry:
    record: dict[str, Any]
    errors: list[str]
    quarantined_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class InMemoryQuarantineStore:
    def __init__(self) -> None:
        self._entries: list[QuarantineEntry] = []

    def add(self, record: dict[str, Any], errors: list[str]) -> QuarantineEntry:
        entry = QuarantineEntry(record=record, errors=errors)
        self._entries.append(entry)
        return entry

    def list_entries(self) -> list[QuarantineEntry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)
