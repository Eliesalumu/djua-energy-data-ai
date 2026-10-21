from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from djua_energy.channels.whatsapp.client import WhatsAppCloudClient
from djua_energy.channels.whatsapp.repository import WhatsAppRepository
from djua_energy.channels.whatsapp.schemas import WebhookPayload
from djua_energy.channels.whatsapp.service import WhatsAppService, bootstrap_admin
from djua_energy.config.runtime import LazyResource
from djua_energy.channels.whatsapp.config import channel_logger, configuration_issues, production, setting

logger = channel_logger("webhook")


class _RedactWebhookQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if str(args[2]).split("?", 1)[0] == "/webhooks/whatsapp":
                args[2] = "/webhooks/whatsapp"
                record.args = tuple(args)
        return True


def create_whatsapp_router(store, chat, *, repository=None, client=None, run_worker=True) -> APIRouter:
    repository = repository or LazyResource(lambda: WhatsAppRepository(store.database_path))
    service = WhatsAppService(repository, store, chat, client or WhatsAppCloudClient())
    logging.getLogger("uvicorn.access").addFilter(_RedactWebhookQuery())

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        await asyncio.to_thread(bootstrap_admin, repository)
        issues = configuration_issues()
        for name in issues:
            logger.error("WHATSAPP configuration missing or invalid: %s", name)
        if not issues:
            logger.info("WHATSAPP configuration valid")

        async def worker():
            while not stop.is_set():
                try:
                    # Keep queued messages pending while production credentials are invalid.
                    worked = False if production() and configuration_issues() else await asyncio.to_thread(service.process_next)
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
        expected = setting("WHATSAPP_VERIFY_TOKEN")
        if mode != "subscribe" or not expected or not challenge or not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(403, "Verification refusee")
        return PlainTextResponse(challenge)

    @router.post("/webhooks/whatsapp")
    async def webhook(request: Request):
        logger.info("WHATSAPP META webhook received")
        secret = setting("WHATSAPP_APP_SECRET")
        if production() and {"WHATSAPP_APP_SECRET", "WHATSAPP_PHONE_NUMBER_ID"}.intersection(configuration_issues()):
            logger.error("WHATSAPP META webhook blocked: signature or phone ID configuration invalid")
            raise HTTPException(503, "Configuration WhatsApp incomplete")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 262144:
                raise HTTPException(413, "Payload trop volumineux")
        if secret:
            expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", "").encode(), expected.encode()):
                logger.warning("WHATSAPP META signature invalid")
                raise HTTPException(403, "Signature invalide")
            logger.info("WHATSAPP META signature valid")
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
                    logger.info("WHATSAPP META ignored: status or empty event")
                    continue
                if value.messaging_product != "whatsapp" or not value.metadata:
                    raise HTTPException(400, "Metadonnees WhatsApp absentes")
                configured_id = setting("WHATSAPP_PHONE_NUMBER_ID")
                if configured_id and value.metadata.phone_number_id != configured_id:
                    logger.warning("WHATSAPP META ignored: phone_number_id mismatch")
                    continue
                logger.info("WHATSAPP META phone_number_id matched=%s", configured_id or "development")
                for message in value.messages:
                    if message.type != "text":
                        continue
                    if not message.text:
                        raise HTTPException(400, "Texte WhatsApp absent")
                    batch.append(message)
        # Durable acceptance only, no LLM or outbound HTTP in the webhook request.
        for message in batch:
            inserted = await asyncio.to_thread(repository.enqueue, message.id, message.sender, message.text.body)
            accepted += int(inserted)
            logger.info("WHATSAPP WORKER %s message_ref=%s", "pending" if inserted else "deduplicated",
                        hashlib.sha256(message.id.encode()).hexdigest()[:12])
        return {"status": "accepted" if accepted else "ignored", "accepted": accepted}

    return router
