from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import random
from typing import Any

import pandas as pd

from djua_energy.features.customer_features import profession_risk_score


PROFESSIONS = [
    "Fonctionnaire",
    "Enseignant",
    "Infirmier",
    "Commercant independant",
    "Chauffeur",
    "Agriculteur",
    "Vendeur de rue",
    "Sans emploi",
]


def generate_historical_customer_dataset(
    output_path: str | Path = "data/generated/customer_scoring_history.csv",
    num_clients: int = 500,
    months_per_client: int = 12,
    seed: int = 42,
) -> pd.DataFrame:
    """Genere un historique mensuel coherent pour entrainer le scoring client."""

    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    start = datetime(2025, 8, 1, tzinfo=UTC)

    for index in range(num_clients):
        client_id = f"ACC-2026-{index + 1:04d}"
        phone = f"084{rng.randint(1000000, 9999999)}"
        profession = rng.choices(PROFESSIONS, weights=[12, 12, 8, 24, 12, 12, 15, 5], k=1)[0]
        profession_risk = profession_risk_score(profession)
        estimated_income = max(55, round(rng.gauss(430 - profession_risk * 260, 85), 2))
        account_age_start = rng.randint(1, 72)
        periodic_amount = rng.choice([8, 10, 15, 20, 25, 30])
        base_risk = min(
            0.95,
            max(
                0.03,
                profession_risk * 0.45
                + (0.2 if estimated_income < 150 else 0)
                + (0.15 if account_age_start < 6 else 0)
                + rng.uniform(-0.08, 0.08),
            ),
        )

        paid_months = rng.randint(0, 4)
        failures = 0
        lates = 0
        missed = 0
        completed = 0
        last_completed_month = -1
        status = "active"

        for month_index in range(months_per_client):
            observation_month = start + pd.DateOffset(months=month_index)
            account_age = account_age_start + month_index
            income_to_fee_ratio = estimated_income / periodic_amount
            monthly_risk = base_risk
            monthly_risk += 0.18 if income_to_fee_ratio < 8 else 0
            monthly_risk += 0.10 if failures >= 2 else 0
            monthly_risk += 0.12 if missed >= 2 else 0
            monthly_risk += 0.12 if status == "suspended" else 0
            monthly_risk = min(0.96, max(0.02, monthly_risk))

            status_roll = rng.random()
            if status_roll < monthly_risk * 0.22:
                payment_status = "missed"
                missed += 1
            elif status_roll < monthly_risk * 0.40:
                payment_status = "late"
                lates += 1
                completed += 1
                paid_months += 1
                last_completed_month = month_index
            elif status_roll < monthly_risk * 0.48:
                payment_status = "failed"
                failures += 1
            else:
                payment_status = "completed"
                completed += 1
                paid_months += 1
                last_completed_month = month_index

            recent_bad_events = failures + missed + max(0, lates - 1)
            status = "suspended" if recent_bad_events >= 3 and rng.random() < 0.55 else "active"
            success_rate = completed / (month_index + 1)
            days_since_last_payment = 365 if last_completed_month < 0 else max(0, (month_index - last_completed_month) * 30)
            avg_payment = periodic_amount * rng.uniform(0.92, 1.08)
            volatility = periodic_amount * min(0.6, monthly_risk)

            default_probability = min(
                0.98,
                max(
                    0.01,
                    monthly_risk * 0.38
                    + (0.34 if status == "suspended" else 0)
                    + (0.18 if days_since_last_payment > 60 else 0)
                    + (0.18 if success_rate < 0.65 else 0)
                    + (0.12 if income_to_fee_ratio < 8 else 0)
                    + (0.08 if account_age < 6 else 0)
                    + rng.uniform(-0.025, 0.025),
                ),
            )
            default_next_90d = int(rng.random() < default_probability)

            rows.append(
                {
                    "client_id": client_id,
                    "phone": phone,
                    "observation_month": observation_month.strftime("%Y-%m"),
                    "profession": profession,
                    "estimated_income_usd": round(estimated_income, 2),
                    "orange_money_account_age_months": account_age,
                    "historical_risk_score": round(base_risk, 3),
                    "paid_months_count": paid_months,
                    "kit_is_suspended": int(status == "suspended"),
                    "payment_success_rate": round(success_rate, 3),
                    "failed_payment_count_12m": failures,
                    "late_payment_count_12m": lates,
                    "missed_payment_count_12m": missed,
                    "days_since_last_payment": days_since_last_payment,
                    "avg_payment_amount_usd": round(avg_payment, 2),
                    "payment_amount_volatility": round(volatility, 2),
                    "income_to_fee_ratio": round(income_to_fee_ratio, 3),
                    "profession_risk_score": round(profession_risk, 3),
                    "default_next_90d": default_next_90d,
                }
            )

    dataset = pd.DataFrame(rows)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)
    return dataset
