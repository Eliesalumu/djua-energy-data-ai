"""Project paths and lazy services: liveness must not depend on models or SQLite."""
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


class LazyResource:
    def __init__(self, factory):
        self._factory = factory
        self._instance = None
        self._lock = Lock()

    def __getattr__(self, name):
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return getattr(self._instance, name)
