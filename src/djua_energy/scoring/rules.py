from __future__ import annotations

from typing import Any


def apply_customer_guardrails(prediction: dict[str, Any]) -> dict[str, Any]:
    """Applique des garde-fous metier autour du score ML."""

    features = prediction.get("features", {})
    adjusted = dict(prediction)
    guardrails: list[str] = []
    probability = float(adjusted["default_probability_90d"])

    if features.get("kit_is_suspended", 0) >= 1 and probability < 0.35:
        probability = 0.35
        guardrails.append("Kit suspendu: le risque minimal est force a moyen.")

    if features.get("payment_success_rate", 1) < 0.5 and probability < 0.45:
        probability = 0.45
        guardrails.append("Taux de paiement reussi inferieur a 50%: risque minimal renforce.")

    if features.get("orange_money_account_age_months", 0) < 3 and adjusted["risk_level"] == "low":
        guardrails.append("Compte Orange Money tres recent: confiance reduite.")

    adjusted["default_probability_90d"] = round(probability, 3)
    adjusted["score"] = max(0, min(100, round((1 - probability) * 100)))
    adjusted["risk_level"] = "high" if probability >= 0.65 else "medium" if probability >= 0.35 else "low"
    adjusted["guardrails"] = guardrails
    return adjusted
