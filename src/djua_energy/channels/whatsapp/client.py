from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .repository import normalize_phone


class WhatsAppSendError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class WhatsAppCloudClient:
    def send_text(self, recipient: str, text: str) -> None:
        token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        version = os.getenv("WHATSAPP_API_VERSION", "")
        if not token or not re.fullmatch(r"[0-9]+", number_id) or not re.fullmatch(r"v[0-9]+\.0", version):
            raise WhatsAppSendError("meta_configuration_missing")
        # Single bounded message avoids partial multi-message deliveries on retries.
        body = {"messaging_product": "whatsapp", "to": normalize_phone(recipient),
                "type": "text", "text": {"preview_url": False, "body": text[:4000]}}
        request = Request(f"https://graph.facebook.com/{version}/{number_id}/messages",
                          data=json.dumps(body).encode("utf-8"), method="POST",
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not payload.get("messages"):
                    raise WhatsAppSendError("meta_delivery_uncertain")
        except HTTPError as exc:
            # Never propagate Meta bodies, headers, or request objects containing credentials.
            raise WhatsAppSendError(f"meta_http_{exc.code}") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise WhatsAppSendError("meta_delivery_uncertain") from None
