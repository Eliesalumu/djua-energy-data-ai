"""In-memory idempotency helpers for the local MVP."""

from __future__ import annotations

from typing import Any


def record_idempotency_key(record: dict[str, Any]) -> str:
    message_id = record.get("message_id")
    if message_id:
        return str(message_id)
    return "|".join(
        str(record.get(field, ""))
        for field in ("device_id", "event_time", "sequence_number")
    )


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(self, record: dict[str, Any]) -> bool:
        return record_idempotency_key(record) in self._seen

    def mark_seen(self, record: dict[str, Any]) -> str:
        key = record_idempotency_key(record)
        self._seen.add(key)
        return key

    def filter_new(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        new_records: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        for record in records:
            if self.is_duplicate(record):
                duplicates.append(record)
            else:
                self.mark_seen(record)
                new_records.append(record)
        return new_records, duplicates
