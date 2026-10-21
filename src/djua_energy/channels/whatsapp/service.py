from __future__ import annotations

import hashlib
import re
import unicodedata

from djua_energy.chat.realtime_context import build_realtime_fleet_context, build_realtime_kit_context
from .client import WhatsAppSendError
from .config import channel_logger, setting

logger = channel_logger("worker")
LOGIC_VERSION = "openai-first-v3"


def bootstrap_admin(repository) -> bool:
    """Reuse the CLI's user upsert in the channel's existing database."""
    phone = setting("WHATSAPP_BOOTSTRAP_PHONE")
    if not phone:
        return False
    try:
        existing = repository.get_user(phone)
        repository.upsert_user(phone, role="admin", display_name="Admin test", active=True,
                               customer_id=existing["customer_id"] if existing else None)
    except Exception:
        # Exception messages and SQL traces may contain the private phone number.
        logger.error("WhatsApp admin bootstrap failed: check WHATSAPP_BOOTSTRAP_PHONE and DJUA_DATABASE_URL")
        return False
    logger.info("WhatsApp admin bootstrap completed")
    return True


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def detect_topic(message: str) -> str:
    text = normalized(message)
    for topic, words in (
        ("history", ("historique", "recent")), ("battery", ("batterie", "battery")),
        ("security", ("securite", "fraude", "sabotage", "boitier")),
        ("connectivity", ("connectivite", "connexion", "reseau")),
        ("consumption", ("consommation", "consomme")), ("production", ("production", "solaire")),
        ("maintenance", ("maintenance", "panne")),
        ("predictions", ("prediction", "prevision")),
    ):
        if any(word in text for word in words):
            return topic
    return "general"


def is_non_data_request(message: str) -> bool:
    # Match complete requests only: an identity prefix must not bypass data permissions.
    text = re.sub(r"[^\w\s]", " ", normalized(message))
    text = " ".join(text.split())
    return text in {
        "tu es qui", "qui es tu", "qui etes vous", "vous etes qui",
        "que peux tu faire", "que pouvez vous faire", "aide", "help",
        "comment fonctionnes tu", "comment fonctionnez vous",
    }


class WhatsAppService:
    def __init__(self, repository, store, chat, client):
        self.repository, self.store, self.chat, self.client = repository, store, chat, client
        logger.info("WHATSAPP DJUA logic_version=%s", LOGIC_VERSION)

    def has_global_access(self, user: dict) -> bool:
        return user["role"] == "admin"

    def answer(self, phone: str, message: str) -> str:
        user = self.repository.get_user(phone)
        logger.info("WHATSAPP DJUA identity found=%s active=%s role=%s", bool(user), bool(user and user["active"]), user["role"] if user else "unknown")
        if not user or not user["active"]:
            logger.warning("WHATSAPP DJUA authorization denied: unknown or inactive account")
            return "Acces refuse. Votre numero n'est pas enregistre ou votre compte est inactif. Contactez le support DJUA ENERGY."
        global_access = self.has_global_access(user)
        intent = "non_data" if is_non_data_request(message) else "data"
        scope_name = "global" if global_access else "granted_devices"
        scope = {"role": user["role"], "customer_id": user["customer_id"], "global_access": global_access}
        logger.info("WHATSAPP DJUA request role=%s intent=%s scope=%s", user["role"], intent, scope_name)
        if intent == "non_data":
            logger.info("WHATSAPP DATA accessible_device_count=0 telemetry_available=false (not requested)")
            return self._reply(message, scope, ("Je suis DJUA Bot, l'assistant de supervision de DJUA ENERGY. "
                    "Je peux vous aider à consulter l'état des kits solaires, la batterie, "
                    "la production, les alertes et les informations disponibles dans votre périmètre d'accès."), "non_data")
        text = normalized(message)
        topic = detect_topic(message)

        # Client lookup is a backend operation, not an instruction delegated to the LLM.
        client_query = re.search(r"\bclient\s+([\w .'-]+)", message, re.I)
        if client_query:
            if not global_access:
                logger.warning("WHATSAPP DJUA authorization denied: customer lookup")
                return self._reply(message, scope, "Acces refuse : la recherche d'autres clients n'est pas autorisee pour votre compte.", "access_denied")
            term = client_query.group(1).strip(" .?!")
            matches = self.repository.search_customers(term)
            exact = [row for row in matches if row["customer_id"].casefold() == term.casefold()]
            matches = exact or matches
            if len({row["customer_id"] for row in matches}) != 1:
                return self._reply(message, scope, "Client introuvable ou recherche ambigue. Precisez son identifiant.", "selection_required")
            customer_id = matches[0]["customer_id"]
            devices = self.repository.devices_for_customer(customer_id)
            context = build_realtime_fleet_context(self.store, [row["device_id"] for row in devices], topic)
            context["access"] = {**scope, "customer_id": customer_id, "device_ids": [row["device_id"] for row in devices]}
            return self._answer_context(message, context)

        if global_access:
            registered = {row["device_id"]: row for row in self.repository.registered_devices()}
            for device_id in self.store.list_observed_device_ids():
                state = self.store.get_device_state(device_id)
                recent = self.store.recent_records_for_device(device_id, limit=1) if not state else []
                registered[device_id] = {"device_id": device_id, "kit_id": (state or (recent[-1] if recent else {})).get("kit_id") or registered.get(device_id, {}).get("kit_id")}
            candidates = list(registered.values())
        else:
            candidates = self.repository.devices_for_user(user["id"])
        logger.info("WHATSAPP DATA accessible_device_count=%s", len(candidates))
        aliases = {}
        for grant in candidates:
            aliases.setdefault(grant["device_id"].casefold(), set()).add(grant["device_id"])
            if grant.get("kit_id"):
                aliases.setdefault(grant["kit_id"].casefold(), set()).add(grant["device_id"])
        requested = set(re.findall(r"\b(?:device|kit)[_-][a-z0-9_-]+\b", message, flags=re.I))
        # Also recognize arbitrary existing IDs (e.g. a UUID or SN123).
        for alias in aliases:
            if re.search(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", message, re.I):
                requested.add(alias)
        for number in re.findall(r"\bdevice\s+(\d+)\b", message, re.I):
            requested.add(f"device-{number}")
        for ref in re.findall(r"\b(?:device|kit)\s+([a-z0-9][a-z0-9_-]*)", message, re.I):
            if ref.casefold() not in {"est", "va", "qui", "que", "du", "de", "a", "au", "solaire", "critique", "normal", "aujourd", "maintenant", "depuis", "pour", "avec", "en", "sans", "et"} and not ref.isdigit():
                requested.add(ref)
        if requested:
            if not global_access and any(ref.casefold() not in aliases for ref in requested):
                logger.warning("WHATSAPP DJUA authorization denied: foreign device")
                return self._reply(message, scope, "Acces refuse : ce device ou kit ne fait pas partie de votre perimetre autorise.", "access_denied")
            if global_access and any(ref.casefold() not in aliases for ref in requested):
                logger.info("WHATSAPP DATA requested device not registered telemetry_available=false")
                return self._reply(message, scope, "Un device ou kit demandé n'est pas enregistré dans le stockage DJUA. Vérifiez son identifiant.", "device_not_found")
            selected = sorted({device_id for ref in requested for device_id in aliases.get(ref.casefold(), {ref})})
        else:
            selected = sorted({row["device_id"] for row in candidates})

        fleet_question = bool(re.search(r"\b(parc|global|globale|tous|toutes|plusieurs|alertes|critiques|kits|devices)\b", text))
        if fleet_question and not global_access and "parc" in text:
            logger.warning("WHATSAPP DJUA authorization denied: global fleet")
            return self._reply(message, scope, "Acces refuse : la situation globale du parc est reservee aux comptes habilites.", "access_denied")
        if not selected:
            logger.info("WHATSAPP DATA telemetry_available=false")
            if global_access:
                return self._reply(message, scope, "Aucun device n'est actuellement enregistré dans le stockage DJUA.", "no_devices")
            return self._reply(message, scope, "Aucun device associe ou aucune donnee disponible dans votre perimetre. Contactez le support pour associer votre kit.", "no_accessible_devices")
        if len(selected) > 1 and not fleet_question and not requested:
            logger.info("WHATSAPP DJUA selection ambiguous device_count=%s", len(selected))
            return self._reply(message, {**scope, "device_ids": selected}, "Vous avez plusieurs kits. Lequel souhaitez-vous consulter ? " + ", ".join(selected[:20]), "selection_required")
        scope["device_ids"] = selected
        if len(selected) == 1 and not (global_access and fleet_question):
            context = {"access": scope, "topic": topic, "kit": build_realtime_kit_context(self.store, selected[0])}
        else:
            context = build_realtime_fleet_context(self.store, selected, topic)
            context["access"] = scope
        return self._answer_context(message, context)

    def _reply(self, message: str, scope: dict, fallback: str, status: str) -> str:
        return self._generate(message, {
            "access": {**scope, "device_ids": scope.get("device_ids", [])},
            "status": status, "telemetry_available": False, "fallback_answer": fallback,
        })

    def _generate(self, message: str, context: dict) -> str:
        context["channel"] = "whatsapp"
        context["assistant"] = {
            "name": "DJUA Bot", "organization": "DJUA ENERGY",
            "capabilities": ["supervision des kits solaires", "batterie", "production", "alertes", "explications et aide"],
        }
        result = self.chat.answer_from_context(message, context)
        logger.info("WHATSAPP DJUA response source=%s", "openai" if getattr(result, "used_llm", False) else "fallback")
        return result.answer

    def _answer_context(self, message: str, context: dict) -> str:
        access = context["access"]
        refs = [hashlib.sha256(device.encode()).hexdigest()[:12] for device in access["device_ids"]]
        logger.info("WHATSAPP DJUA authorization granted role=%s device_refs=%s", access["role"], ",".join(refs[:10]))
        available = context["kit"]["telemetry_available"] if "kit" in context else context["telemetry_available"]
        logger.info("WHATSAPP DATA role=%s intent=data scope=%s accessible_device_count=%s telemetry_available=%s",
                    access["role"], "global" if access["global_access"] else "granted_devices",
                    len(access["device_ids"]), str(available).lower())
        if access["global_access"] and not available:
            if not access["device_ids"]:
                return self._reply(message, access, "Aucun device n'est enregistré pour ce client dans le stockage DJUA.", "no_devices")
            return self._reply(message, access, "Des devices sont enregistrés, mais aucune télémétrie exploitable n'est actuellement disponible.", "no_telemetry")
        return self._generate(message, context)

    def process_next(self) -> bool:
        message = self.repository.claim_next()
        if not message:
            return False
        message_id = message["message_id"]
        ref = hashlib.sha256(message_id.encode()).hexdigest()[:12]
        logger.info("WHATSAPP WORKER processing message_ref=%s", ref)
        try:
            answer = self.answer(message["phone_number"], message["body"])
            # Persist before the network call; never automatically resend uncertain deliveries.
            self.repository.update_message(message_id, "sending", response=answer)
            logger.info("WHATSAPP WORKER sending message_ref=%s", ref)
            self.client.send_text(message["phone_number"], answer)
            self.repository.update_message(message_id, "sent")
            logger.info("WHATSAPP WORKER sent message_ref=%s", ref)
        except WhatsAppSendError as exc:
            status = "uncertain" if exc.code == "meta_delivery_uncertain" or exc.code.startswith("meta_http_5") else "failed"
            self.repository.update_message(message_id, status, error_code=exc.code)
            logger.warning("WHATSAPP WORKER %s message_ref=%s code=%s", status, ref, exc.code)
        except Exception:
            self.repository.update_message(message_id, "failed", error_code="processing_failed")
            logger.error("WHATSAPP WORKER failed message_ref=%s code=processing_failed", ref)
        return True
