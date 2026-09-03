from __future__ import annotations

import os
from typing import Any


def local_score_explanation(prediction: dict[str, Any], external_data: dict[str, Any]) -> dict[str, Any]:
    features = prediction.get("features", {})
    factors: list[str] = []

    if features.get("historical_risk_score", 0) >= 0.55:
        factors.append("Risque historique client eleve.")
    if features.get("kit_is_suspended", 0) >= 1:
        factors.append("Kit actuellement suspendu.")
    if features.get("payment_success_rate", 1) < 0.7:
        factors.append("Taux de paiements reussis faible.")
    if features.get("days_since_last_payment", 0) > 60:
        factors.append("Dernier paiement trop ancien.")
    if features.get("income_to_fee_ratio", 99) < 8:
        factors.append("Charge d'abonnement elevee par rapport au revenu estime.")
    if not factors:
        factors.append("Historique de paiement et profil client globalement favorables.")

    recommendation = "eligible"
    if prediction["risk_level"] == "high":
        recommendation = "review_required"
    elif prediction["risk_level"] == "medium":
        recommendation = "eligible_with_monitoring"

    return {
        "provider": "local",
        "summary": (
            f"Score {prediction['score']}/100, risque {prediction['risk_level']}, "
            f"probabilite de defaut a 90 jours {prediction['default_probability_90d']}."
        ),
        "main_factors": factors[:5],
        "recommendation": recommendation,
    }


def llm_score_explanation(prediction: dict[str, Any], external_data: dict[str, Any]) -> dict[str, Any]:
    """Produit une explication LLM si la cle OpenAI et le SDK sont disponibles."""

    if not os.getenv("OPENAI_API_KEY"):
        fallback = local_score_explanation(prediction, external_data)
        fallback["warning"] = "OPENAI_API_KEY absente: explication locale utilisee."
        return fallback

    try:
        from openai import OpenAI
    except ImportError:
        fallback = local_score_explanation(prediction, external_data)
        fallback["warning"] = "SDK openai non installe: explication locale utilisee."
        return fallback

    client = OpenAI()
    compact_payload = {
        "prediction": {
            "score": prediction["score"],
            "risk_level": prediction["risk_level"],
            "default_probability_90d": prediction["default_probability_90d"],
            "guardrails": prediction.get("guardrails", []),
        },
        "features": prediction.get("features", {}),
        "client": external_data.get("data", external_data).get("client", {}),
        "subscription": external_data.get("data", external_data).get("subscription", {}),
    }
    response = client.responses.create(
        model=os.getenv("DJUA_OPENAI_MODEL", "gpt-5-mini"),
        instructions=(
            "Tu es un analyste risque pour DJUA ENERGY. Explique le score client en francais simple, "
            "sans inventer de donnees, sans donner de decision de credit definitive, et avec une recommandation operationnelle."
        ),
        input=f"Explique ce score client en 4 phrases maximum:\n{compact_payload}",
        store=False,
    )
    return {
        "provider": "openai",
        "summary": response.output_text,
        "main_factors": local_score_explanation(prediction, external_data)["main_factors"],
        "recommendation": local_score_explanation(prediction, external_data)["recommendation"],
    }
