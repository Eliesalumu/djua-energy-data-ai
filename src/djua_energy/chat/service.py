from __future__ import annotations

import json
import os
from dataclasses import dataclass
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


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


@dataclass
class ChatResult:
    answer: str
    intent: str
    device_id: str | None
    used_llm: bool
    context: dict[str, Any]
    sources: list[str]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
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
        timeout_seconds: int = 45,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout_seconds = timeout_seconds

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
            "temperature": 0.2,
            "max_output_tokens": 450,
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
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
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
    return f"OpenAI indisponible: {exc}"


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
        f"{indicators['battery_age_months']} mois, monte jusqu'a "
        f"{indicators['max_battery_temperature_c']} C, descend jusqu'a "
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
        self.dataset = dataset if dataset is not None else load_dataset()
        self.engine = engine or LocalInferenceEngine("artifacts")
        self.llm_client = llm_client or OpenAIResponsesClient()

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
            except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
                return ChatResult(
                    answer=fallback(context),
                    intent=query.intent,
                    device_id=query.device_id,
                    used_llm=False,
                    context=context,
                    sources=sources,
                    error=_friendly_llm_error(exc),
                )

        return ChatResult(
            answer=fallback(context),
            intent=query.intent,
            device_id=query.device_id,
            used_llm=False,
            context=context,
            sources=sources,
            error="OPENAI_API_KEY absente; reponse locale de secours utilisee.",
        )
