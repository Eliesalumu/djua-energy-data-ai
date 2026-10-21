from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from djua_energy.chat.context_builder import (
    build_device_context,
    build_fleet_context,
    extract_device_query,
    load_dataset,
)
from djua_energy.chat.prompts import SYSTEM_PROMPT, build_user_prompt
from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.config.openai_settings import configured_api_key, configured_model, configured_timeout, generation_options
from djua_energy.config.runtime import LazyResource

logger = logging.getLogger(__name__)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
LOCAL_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def _configured_api_key() -> str | None:
    """Read the local secret on every request so key rotation reaches running servers."""
    return configured_api_key(LOCAL_ENV_PATH)


@dataclass
class ChatResult:
    answer: str
    intent: str
    device_id: str | None
    used_llm: bool
    context: dict[str, Any]
    sources: list[str]
    error: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": "ai" if self.used_llm else "local",
            "warning": {"code": self.error_code or "AI_UNAVAILABLE", "message": self.error} if self.error else None,
            "answer": self.answer,
            "intent": self.intent,
            "device_id": self.device_id,
            "used_llm": self.used_llm,
            "sources": self.sources,
            "context": self.context,
            "error": self.error,
        }


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model or configured_model()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else configured_timeout()

    @property
    def api_key(self) -> str | None:
        return self._api_key if self._api_key is not None else _configured_api_key()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, message: str, context: dict[str, Any]) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY est absente de l'environnement.")

        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        message,
                        json.dumps(context, ensure_ascii=False, indent=2),
                    ),
                },
            ],
            **generation_options(self.model, 450),
        }
        request = Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        logger.info("AI_PROVIDER request starting")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            logger.info("AI_PROVIDER completed")
        except Exception as exc:
            logger.warning("AI_PROVIDER failed code=%s", _llm_error_code(exc))
            raise
        return _extract_output_text(payload)


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()
    texts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                texts.append(str(content["text"]))
    if texts:
        return "\n".join(texts).strip()
    raise RuntimeError("La reponse OpenAI ne contient pas de texte exploitable.")


def _llm_error_code(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return {401: "AI_AUTHENTICATION_ERROR", 403: "AI_PERMISSION_ERROR", 429: "AI_RATE_LIMIT"}.get(exc.code, "AI_PROVIDER_ERROR")
    if isinstance(exc, TimeoutError):
        return "AI_TIMEOUT"
    if isinstance(exc, URLError):
        return "AI_NETWORK_ERROR"
    return "AI_PROVIDER_ERROR"


def _friendly_llm_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code == 429:
            return "OpenAI indisponible temporairement: quota ou rate limit atteint."
        if exc.code == 401:
            return "OpenAI indisponible: cle API absente ou invalide."
        return f"OpenAI indisponible: erreur HTTP {exc.code}."
    if isinstance(exc, URLError):
        return "OpenAI indisponible: connexion reseau bloquee ou impossible."
    if isinstance(exc, TimeoutError):
        return "OpenAI indisponible: delai de reponse depasse."
    return "OpenAI indisponible: reponse inexploitable ou erreur du fournisseur."


def _fallback_device_answer(context: dict[str, Any]) -> str:
    if not context.get("found"):
        examples = ", ".join(context.get("available_examples", []))
        return f"Je ne trouve pas {context.get('device_id')}. Exemples disponibles : {examples}."

    indicators = context["indicators"]
    cases = ", ".join(context["detected_cases"])
    security = []
    if indicators["enclosure_opened"]:
        security.append("ouverture du boitier")
    if indicators["tamper_detected"]:
        security.append("tamper")
    if indicators["movement_detected"]:
        security.append("mouvement anormal")
    security_sentence = f" Cote securite, l'IA observe {', '.join(security)}." if security else ""
    if context["global_status"] == "normal":
        return (
            f"Le device {context['device_id']} est dans un etat normal. "
            f"L'IA a analyse {indicators['measure_count']} mesures et ne detecte pas de probleme critique. "
            "Action recommandee : continuer la surveillance standard."
        )
    return (
        f"Le device {context['device_id']} est dans un etat {context['global_status']}. "
        f"L'IA a detecte : {cases}. La connectivite descend jusqu'a un silence de "
        f"{indicators['max_connectivity_gap_seconds']} secondes. La batterie, agee de "
        f"{indicators['battery_age_months']} mois, descend jusqu'a "
        f"{indicators['min_battery_voltage_v']} V et atteint un minimum de charge de "
        f"{indicators['min_state_of_charge_pct']} %. La production solaire descend jusqu'a "
        f"{indicators['min_solar_power_w']} W.{security_sentence} "
        "Action recommandee : ouvrir une intervention prioritaire, verifier le boitier, "
        "controler la batterie et retablir la connectivite."
    )


def _fallback_fleet_answer(context: dict[str, Any], intent: str) -> str:
    if intent == "normal_devices":
        devices = ", ".join(context["normal_devices"]) or "aucun"
        return f"Les devices en etat normal dans le dataset sont : {devices}."
    if intent == "critical_devices":
        examples = ", ".join(context["critical_devices"][:10])
        return (
            f"Le dataset contient {len(context['critical_devices'])} devices critiques. "
            f"Exemples : {examples}."
        )
    return (
        f"Le parc contient {context['device_count']} devices. "
        f"Devices normaux : {', '.join(context['normal_devices']) or 'aucun'}. "
        f"Devices critiques : {len(context['critical_devices'])}."
    )


class DjuaChatService:
    def __init__(
        self,
        *,
        dataset: pd.DataFrame | None = None,
        engine: LocalInferenceEngine | None = None,
        llm_client: OpenAIResponsesClient | None = None,
    ) -> None:
        self._dataset = dataset
        self._dataset_lock = Lock()
        self.engine = engine or LazyResource(LocalInferenceEngine)
        self.llm_client = llm_client or OpenAIResponsesClient()

    @property
    def dataset(self) -> pd.DataFrame:
        if self._dataset is None:
            with self._dataset_lock:
                if self._dataset is None:
                    self._dataset = load_dataset()
        return self._dataset

    def answer_from_context(self, message: str, context: dict[str, Any]) -> ChatResult:
        """Answer with an already authorized realtime context, with no CSV fallback."""
        from djua_energy.chat.realtime_context import realtime_fallback

        fallback = realtime_fallback(context)
        if ("kit" in context and not context["kit"]["found"]) or context.get("device_count") == 0:
            return ChatResult(fallback, "realtime", context.get("kit", {}).get("device_id"), False,
                              context, ["RealtimeTelemetryStore"], "Donnees indisponibles.")
        if self.llm_client.available:
            try:
                answer = self.llm_client.generate(
                    message + "\nRespecte le role et le perimetre fournis. Client: court, simple et actionnable. "
                    "Admin: chiffres calcules et priorites. Technicien: details disponibles. "
                    "Distingue observations, predictions, simulation et donnees absentes. Ne deduis jamais une cause certaine.", context)
                return ChatResult(answer, "realtime", context.get("kit", {}).get("device_id"), True,
                                  context, ["RealtimeTelemetryStore"])
            except Exception as exc:
                error = _friendly_llm_error(exc)
        else:
            error = "OpenAI indisponible; reponse locale fondee sur les donnees autorisees."
        return ChatResult(fallback, "realtime", context.get("kit", {}).get("device_id"), False,
                          context, ["RealtimeTelemetryStore"], error)

    def answer(self, message: str) -> ChatResult:
        query = extract_device_query(message)
        if query.device_id:
            context = build_device_context(query.device_id, dataset=self.dataset, engine=self.engine)
            sources = list(context.get("data_sources", [context.get("data_source", "dataset")]))
            fallback = _fallback_device_answer
        else:
            context = build_fleet_context(dataset=self.dataset)
            sources = [context["data_source"]]
            fallback = lambda data: _fallback_fleet_answer(data, query.intent)

        if self.llm_client.available:
            try:
                answer = self.llm_client.generate(message, context)
                return ChatResult(
                    answer=answer,
                    intent=query.intent,
                    device_id=query.device_id,
                    used_llm=True,
                    context=context,
                    sources=sources,
                )
            except Exception as exc:  # noqa: BLE001 - le chat doit toujours retomber sur la reponse locale.
                return ChatResult(
                    answer=fallback(context),
                    intent=query.intent,
                    device_id=query.device_id,
                    used_llm=False,
                    context=context,
                    sources=sources,
                    error=_friendly_llm_error(exc),
                    error_code=_llm_error_code(exc),
                )

        return ChatResult(
            answer=fallback(context),
            intent=query.intent,
            device_id=query.device_id,
            used_llm=False,
            context=context,
            sources=sources,
            error="OPENAI_API_KEY absente; reponse locale de secours utilisee.",
            error_code="AI_NOT_CONFIGURED",
        )
