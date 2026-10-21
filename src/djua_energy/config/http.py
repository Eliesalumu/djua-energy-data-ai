import json
import os
from urllib.parse import urlsplit


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    try:
        configured = json.loads(raw) if raw.startswith("[") else raw.split(",")
    except ValueError:
        raise ValueError("CORS_ORIGINS doit etre une liste JSON ou une liste separee par des virgules.") from None
    if not isinstance(configured, list) or any(not isinstance(value, str) for value in configured):
        raise ValueError("CORS_ORIGINS doit contenir uniquement des origins HTTP.")
    values = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"]
    for value in [*configured, os.getenv("FRONTEND_URL", "")]:
        value = value.strip().rstrip("/")
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password or "*" in value:
            raise ValueError("FRONTEND_URL/CORS_ORIGINS doivent contenir des origins HTTP exactes, sans chemin ni wildcard.")
        values.append(value)
    return list(dict.fromkeys(values))
