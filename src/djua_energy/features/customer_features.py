from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd


CUSTOMER_SCORING_FEATURES = [
    "estimated_income_usd",
    "orange_money_account_age_months",
    "historical_risk_score",
    "paid_months_count",
    "kit_is_suspended",
    "payment_success_rate",
    "failed_payment_count_12m",
    "late_payment_count_12m",
    "missed_payment_count_12m",
    "days_since_last_payment",
    "avg_payment_amount_usd",
    "payment_amount_volatility",
    "income_to_fee_ratio",
    "profession_risk_score",
]


PROFESSION_RISK_SCORES = {
    "fonctionnaire": 0.18,
    "enseignant": 0.22,
    "infirmier": 0.24,
    "commercant independant": 0.36,
    "commerçant indépendant": 0.36,
    "chauffeur": 0.42,
    "agriculteur": 0.46,
    "vendeur de rue": 0.62,
    "sans emploi": 0.78,
}


def _normalise_profession(value: str | None) -> str:
    return (value or "").strip().lower()


def profession_risk_score(value: str | None) -> float:
    profession = _normalise_profession(value)
    return PROFESSION_RISK_SCORES.get(profession, 0.5)


def build_customer_features_from_external_payload(payload: dict[str, Any], reference_time: datetime | None = None) -> pd.DataFrame:
    """Transforme la reponse /api/external/scoring-data/:phone en features ML."""

    data = payload.get("data", payload)
    client = data.get("client", {})
    subscription = data.get("subscription", {})
    payments = data.get("paymentHistory", []) or []
    reference_time = reference_time or datetime.now(tz=UTC)

    payment_amounts = [float(payment.get("amountUSD", 0) or 0) for payment in payments]
    completed_payments = [payment for payment in payments if payment.get("status") == "completed"]
    failed_count = sum(1 for payment in payments if payment.get("status") in {"failed", "rejected"})
    late_count = sum(1 for payment in payments if payment.get("status") == "late")
    missed_count = sum(1 for payment in payments if payment.get("status") in {"missed", "pending"})

    payment_dates = []
    for payment in completed_payments:
        raw_date = payment.get("date")
        if not raw_date:
            continue
        try:
            payment_dates.append(datetime.fromisoformat(raw_date.replace("Z", "+00:00")))
        except ValueError:
            continue

    if payment_dates:
        days_since_last_payment = max(0, (reference_time - max(payment_dates)).days)
    else:
        days_since_last_payment = 365

    periodic_amount = float(subscription.get("periodicAmountUSD") or subscription.get("periodic_amount_usd") or 0)
    estimated_income = float(client.get("estimatedIncomeUSD") or client.get("estimated_income_usd") or 0)
    if not periodic_amount and payment_amounts:
        periodic_amount = float(pd.Series(payment_amounts).median())

    avg_payment_amount = float(pd.Series(payment_amounts).mean()) if payment_amounts else 0.0
    payment_volatility = float(pd.Series(payment_amounts).std()) if len(payment_amounts) > 1 else 0.0
    success_rate = len(completed_payments) / len(payments) if payments else 0.0

    row = {
        "estimated_income_usd": estimated_income,
        "orange_money_account_age_months": float(client.get("orangeMoneyAccountAgeMonths") or 0),
        "historical_risk_score": float(client.get("historicalRiskScore") or 0.5),
        "paid_months_count": float(subscription.get("paidMonthsCount") or 0),
        "kit_is_suspended": 1.0 if subscription.get("status") == "suspended" else 0.0,
        "payment_success_rate": success_rate,
        "failed_payment_count_12m": float(failed_count),
        "late_payment_count_12m": float(late_count),
        "missed_payment_count_12m": float(missed_count),
        "days_since_last_payment": float(days_since_last_payment),
        "avg_payment_amount_usd": avg_payment_amount,
        "payment_amount_volatility": payment_volatility,
        "income_to_fee_ratio": estimated_income / periodic_amount if periodic_amount > 0 else 0.0,
        "profession_risk_score": profession_risk_score(client.get("profession")),
    }
    return pd.DataFrame([row], columns=CUSTOMER_SCORING_FEATURES)
