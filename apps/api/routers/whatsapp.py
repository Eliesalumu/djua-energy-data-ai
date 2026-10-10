from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from djua_energy.channels.whatsapp.client import WhatsAppCloudClient
from djua_energy.channels.whatsapp.repository import WhatsAppRepository
from djua_energy.channels.whatsapp.schemas import WebhookPayload
from djua_energy.channels.whatsapp.service import WhatsAppService


class _RedactWebhookQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if str(args[2]).split("?", 1)[0] == "/webhooks/whatsapp":
                args[2] = "/webhooks/whatsapp"
                record.args = tuple(args)
        return True


def create_whatsapp_router(store, chat, *, repository=None, client=None, run_worker=True) -> APIRouter:
    repository = repository or WhatsAppRepository(store.database_path)
    service = WhatsAppService(repository, store, chat, client or WhatsAppCloudClient())
    logging.getLogger("uvicorn.access").addFilter(_RedactWebhookQuery())

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def worker():
            while not stop.is_set():
                try:
                    worked = await asyncio.to_thread(service.process_next)
                except Exception:
                    logging.getLogger(__name__).error("WhatsApp worker: database operation failed")
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=1)
                    except TimeoutError:
                        pass

        task = asyncio.create_task(worker()) if run_worker else None
        try:
            yield
        finally:
            stop.set()
            if task:
                await task

    router = APIRouter(tags=["WhatsApp"], lifespan=lifespan)

    @router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
    def verify(mode: str = Query("", alias="hub.mode"),
               token: str = Query("", alias="hub.verify_token"),
               challenge: str = Query("", alias="hub.challenge")):
        expected = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        if mode != "subscribe" or not expected or not challenge or not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(403, "Verification refusee")
        return PlainTextResponse(challenge)

    @router.post("/webhooks/whatsapp")
    async def webhook(request: Request):
        secret = os.getenv("WHATSAPP_APP_SECRET", "")
        production = bool(os.getenv("RENDER")) or os.getenv("DJUA_ENV") == "production"
        if production and (not secret or not os.getenv("WHATSAPP_PHONE_NUMBER_ID")):
            raise HTTPException(503, "Configuration WhatsApp incomplete")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 262144:
                raise HTTPException(413, "Payload trop volumineux")
        if secret:
            expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", "").encode(), expected.encode()):
                raise HTTPException(403, "Signature invalide")
        try:
            payload = WebhookPayload.model_validate_json(raw)
        except ValidationError:
            # Do not echo invalid inputs: they may contain private data.
            raise HTTPException(400, "Payload WhatsApp invalide") from None
        accepted = 0
        if payload.object != "whatsapp_business_account":
            return {"status": "ignored", "accepted": 0}
        batch = []
        for entry in payload.entry:
            for change in entry.changes:
                value = change.value
                if change.field != "messages" or not value.messages:
                    continue
                if value.messaging_product != "whatsapp" or not value.metadata:
                    raise HTTPException(400, "Metadonnees WhatsApp absentes")
                configured_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
                if configured_id and value.metadata.phone_number_id != configured_id:
                    continue
                for message in value.messages:
                    if message.type != "text":
                        continue
                    if not message.text:
                        raise HTTPException(400, "Texte WhatsApp absent")
                    batch.append(message)
        # Durable acceptance only, no LLM or outbound HTTP in the webhook request.
        for message in batch:
            accepted += int(await asyncio.to_thread(repository.enqueue, message.id, message.sender, message.text.body))
        return {"status": "accepted" if accepted else "ignored", "accepted": accepted}

    return router
