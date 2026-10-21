"""Read Render configuration without ever exposing secret values."""
import os
import re
import logging

REQUIRED_SETTINGS = ("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID",
                     "WHATSAPP_API_VERSION", "WHATSAPP_APP_SECRET")


def channel_logger(component: str) -> logging.Logger:
    """Expose channel INFO events under uvicorn without changing global logging."""
    channel = logging.getLogger("djua.whatsapp")
    channel.setLevel(logging.INFO)
    if not channel.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        channel.addHandler(handler)
    return channel.getChild(component)


def setting(name: str) -> str:
    return os.getenv(name, "").strip()


def production() -> bool:
    return bool(os.getenv("RENDER")) or os.getenv("DJUA_ENV") == "production"


def configuration_issues() -> list[str]:
    """Return variable names only, never values or provider error bodies."""
    issues = [name for name in REQUIRED_SETTINGS if not setting(name)
              or (setting(name).startswith("<") and setting(name).endswith(">"))]
    for name, pattern in (("WHATSAPP_PHONE_NUMBER_ID", r"[0-9]+"), ("WHATSAPP_API_VERSION", r"v[0-9]+\.0")):
        if name not in issues and not re.fullmatch(pattern, setting(name)):
            issues.append(name)
    return issues
