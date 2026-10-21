"""Project paths and lazy services: liveness must not depend on models or SQLite."""
from pathlib import Path
from threading import Lock
from importlib.util import find_spec


def _resolve_project_root() -> Path:
    source_root = Path(__file__).resolve().parents[3]
    if (source_root / "apps/api/main.py").is_file():
        return source_root
    # Native deployments may install djua_energy inside a virtualenv, while
    # the ASGI entry point and resources remain in the actual checkout.
    try:
        spec = find_spec("apps.api.main")
    except (ImportError, ValueError):
        spec = None
    if spec and spec.origin:
        return Path(spec.origin).resolve().parents[2]
    return source_root


PROJECT_ROOT = _resolve_project_root()


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
