"""Shared server-side OpenAI configuration for both assistants."""
import os
from pathlib import Path

LOCAL_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def configured_api_key(path: Path | None = None) -> str | None:
    # Hosted environments must use their own secret, never a developer's .env.
    if os.getenv("RENDER") or os.getenv("DJUA_ENV") == "production":
        return os.getenv("OPENAI_API_KEY")
    path = path if path is not None else LOCAL_ENV_PATH
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.strip() == "OPENAI_API_KEY":
                return value.strip().strip("\"'") or None
    return os.getenv("OPENAI_API_KEY")


def configured_model() -> str:
    return os.getenv("DJUA_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"


def generation_options(model: str, max_output_tokens: int) -> dict:
    # Reasoning models do not accept the temperature used by GPT-4 models.
    if model.startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_output_tokens": max(3000, max_output_tokens)}
    return {"temperature": 0.2, "max_output_tokens": max_output_tokens}
