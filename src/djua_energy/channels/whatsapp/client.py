from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .repository import normalize_phone
from .config import channel_logger, configuration_issues, setting

logger = channel_logger("graph")


class WhatsAppSendError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class WhatsAppCloudClient:
    def send_text(self, recipient: str, text: str) -> None:
        token = setting("WHATSAPP_ACCESS_TOKEN")
        number_id = setting("WHATSAPP_PHONE_NUMBER_ID")
        version = setting("WHATSAPP_API_VERSION")
        if {"WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_API_VERSION"}.intersection(configuration_issues()):
            raise WhatsAppSendError("meta_configuration_missing")
        # Single bounded message avoids partial multi-message deliveries on retries.
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": normalize_phone(recipient),
                "type": "text", "text": {"preview_url": False, "body": text[:4000]}}
        request = Request(f"https://graph.facebook.com/{version}/{number_id}/messages",
                          data=json.dumps(body).encode("utf-8"), method="POST",
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            logger.info("WHATSAPP META graph request phone_number_id=%s version=%s", number_id, version)
            with urlopen(request, timeout=25) as response:
                logger.info("WHATSAPP META graph HTTP status=%s", getattr(response, "status", 200))
                payload = json.loads(response.read().decode("utf-8"))
                if not payload.get("messages"):
                    raise WhatsAppSendError("meta_delivery_uncertain")
        except HTTPError as exc:
            logger.warning("WHATSAPP META graph HTTP status=%s", exc.code)
            # Never propagate Meta bodies, headers, or request objects containing credentials.
            raise WhatsAppSendError(f"meta_http_{exc.code}") from None
        except (URLError, TimeoutError, OSError, ValueError):
            logger.warning("WHATSAPP META graph delivery uncertain")
            raise WhatsAppSendError("meta_delivery_uncertain") from None
