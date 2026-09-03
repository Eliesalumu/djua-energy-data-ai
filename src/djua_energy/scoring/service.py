from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from djua_energy.features.customer_features import build_customer_features_from_external_payload
from djua_energy.scoring.decision_engine import CustomerDecisionEngine
from djua_energy.scoring.explainability import llm_score_explanation, local_score_explanation
from djua_energy.scoring.model import CustomerScoringModel
from djua_energy.scoring.rules import apply_customer_guardrails


class ExternalScoringApiClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 8.0):
        self.base_url = (base_url or os.getenv("DJUA_EXTERNAL_API_BASE_URL") or "").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_scoring_data(self, phone: str) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("DJUA_EXTERNAL_API_BASE_URL n'est pas configure.")

        url = f"{self.base_url}/api/external/scoring-data/{phone}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"API externe indisponible pour {phone}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Impossible de joindre l'API externe: {exc.reason}") from exc

        payload = json.loads(body)
        if not payload.get("success", False):
            raise RuntimeError(f"API externe a retourne une reponse non succes: {payload}")
        return payload


class CustomerScoringService:
    def __init__(
        self,
        model: CustomerScoringModel | None = None,
        external_api_client: ExternalScoringApiClient | None = None,
        decision_engine: CustomerDecisionEngine | None = None,
    ):
        self.model = model
        self.external_api_client = external_api_client or ExternalScoringApiClient()
        self.decision_engine = decision_engine or CustomerDecisionEngine()

    def score_from_external_api(self, phone: str, explain_with_llm: bool = False) -> dict[str, Any]:
        external_payload = self.external_api_client.get_scoring_data(phone)
        return self.score_payload(external_payload, explain_with_llm=explain_with_llm)

    def score_payload(self, external_payload: dict[str, Any], explain_with_llm: bool = False) -> dict[str, Any]:
        features = build_customer_features_from_external_payload(external_payload)
        model = self._customer_scoring_model()
        prediction = model.predict(features)
        prediction = apply_customer_guardrails(prediction)
        explanation = (
            llm_score_explanation(prediction, external_payload)
            if explain_with_llm
            else local_score_explanation(prediction, external_payload)
        )
        data = external_payload.get("data", external_payload)
        client = data.get("client", {})
        subscription = data.get("subscription", {})

        return {
            "phone": client.get("phone") or data.get("phone"),
            "account_number": client.get("accountNumber"),
            "client_name": " ".join(part for part in [client.get("firstName"), client.get("lastName")] if part),
            "subscription": {
                "kit_id": subscription.get("kitId"),
                "offer_name": subscription.get("offerName"),
                "status": subscription.get("status"),
                "paid_months_count": subscription.get("paidMonthsCount"),
            },
            "score": prediction["score"],
            "risk_level": prediction["risk_level"],
            "default_probability_90d": prediction["default_probability_90d"],
            "decision": explanation["recommendation"],
            "main_factors": explanation["main_factors"],
            "explanation": explanation,
            "features": prediction["features"],
            "guardrails": prediction.get("guardrails", []),
            "model": {
                "name": "customer_scoring",
                "version": prediction["model_version"],
                "trained_on_synthetic_data": True,
            },
        }

    def evaluate_customer_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Evalue un snapshot Backend -> IA deja resolu cote identite metier."""

        return self.decision_engine.evaluate(payload)

    def _customer_scoring_model(self) -> CustomerScoringModel:
        if self.model is None:
            self.model = CustomerScoringModel()
        return self.model
