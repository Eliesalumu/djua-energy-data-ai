from __future__ import annotations

import os
import re
import unicodedata

from djua_energy.chat.realtime_context import build_realtime_fleet_context, build_realtime_kit_context
from .client import WhatsAppSendError


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


class WhatsAppService:
    def __init__(self, repository, store, chat, client):
        self.repository, self.store, self.chat, self.client = repository, store, chat, client

    def has_global_access(self, user: dict) -> bool:
        # Customer is never eligible for elevation by configuration.
        configured = set(os.getenv("WHATSAPP_GLOBAL_ROLES", "").split(",")) & {"technician", "support"}
        return user["role"] == "admin" or user["role"] in configured

    def answer(self, phone: str, message: str) -> str:
        user = self.repository.get_user(phone)
        if not user or not user["active"]:
            return "Acces refuse. Votre numero n'est pas enregistre ou votre compte est inactif. Contactez le support DJUA ENERGY."
        global_access = self.has_global_access(user)
        grants = self.repository.devices_for_user(user["id"])
        text = normalized(message)
        topic = detect_topic(message)
        scope = {"role": user["role"], "customer_id": user["customer_id"], "global_access": global_access}

        # Client lookup is a backend operation, not an instruction delegated to the LLM.
        client_query = re.search(r"\bclient\s+([\w .'-]+)", message, re.I)
        if client_query:
            if not global_access:
                return "Acces refuse : la recherche d'autres clients n'est pas autorisee pour votre compte."
            term = client_query.group(1).strip(" .?!")
            matches = self.repository.search_customers(term)
            exact = [row for row in matches if row["customer_id"].casefold() == term.casefold()]
            matches = exact or matches
            if len({row["customer_id"] for row in matches}) != 1:
                return "Client introuvable ou recherche ambigue. Precisez son identifiant. " + ", ".join(sorted({row["customer_id"] for row in matches}))
            customer_id = matches[0]["customer_id"]
            devices = self.repository.devices_for_customer(customer_id)
            context = build_realtime_fleet_context(self.store, [row["device_id"] for row in devices], topic)
            context["access"] = {**scope, "customer_id": customer_id, "device_ids": [row["device_id"] for row in devices]}
            return self.chat.answer_from_context(message, context).answer

        candidates = grants
        if global_access:
            candidates = []
            for device_id in self.store.list_observed_device_ids():
                state = self.store.get_device_state(device_id)
                recent = self.store.recent_records_for_device(device_id, limit=1) if not state else []
                candidates.append({"device_id": device_id, "kit_id": (state or (recent[-1] if recent else {})).get("kit_id")})
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
                return "Acces refuse : ce device ou kit ne fait pas partie de votre perimetre autorise."
            selected = sorted({device_id for ref in requested for device_id in aliases.get(ref.casefold(), {ref})})
        else:
            selected = sorted({row["device_id"] for row in candidates})

        fleet_question = bool(re.search(r"\b(parc|global|globale|tous|toutes|plusieurs|alertes|critiques|kits|devices)\b", text))
        if fleet_question and not global_access and "parc" in text:
            return "Acces refuse : la situation globale du parc est reservee aux comptes habilites."
        if not selected:
            return "Aucun device associe ou aucune donnee disponible dans votre perimetre. Contactez le support pour associer votre kit."
        if len(selected) > 1 and not fleet_question and not requested:
            return "Vous avez plusieurs kits. Lequel souhaitez-vous consulter ? " + ", ".join(selected[:20])
        scope["device_ids"] = selected
        if len(selected) == 1 and not (global_access and fleet_question):
            context = {"access": scope, "topic": topic, "kit": build_realtime_kit_context(self.store, selected[0])}
        else:
            context = build_realtime_fleet_context(self.store, selected, topic)
            context["access"] = scope
        return self.chat.answer_from_context(message, context).answer

    def process_next(self) -> bool:
        message = self.repository.claim_next()
        if not message:
            return False
        message_id = message["message_id"]
        try:
            answer = self.answer(message["phone_number"], message["body"])
            # Persist before the network call; never automatically resend uncertain deliveries.
            self.repository.update_message(message_id, "sending", response=answer)
            self.client.send_text(message["phone_number"], answer)
            self.repository.update_message(message_id, "sent")
        except WhatsAppSendError as exc:
            status = "uncertain" if exc.code == "meta_delivery_uncertain" or exc.code.startswith("meta_http_5") else "failed"
            self.repository.update_message(message_id, status, error_code=exc.code)
        except Exception:
            self.repository.update_message(message_id, "failed", error_code="processing_failed")
        return True
