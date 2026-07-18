"""In-memory counters for the local MVP."""

from __future__ import annotations

from collections import Counter


class InMemoryMetrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()

    def increment(self, name: str, value: int = 1) -> None:
        self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        return dict(self._counters)
