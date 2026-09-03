from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.solar_advisor.service import SolarAdvisorService


SCENARIOS = [
    {
        "scenario": "petit_menage",
        "city": "kinshasa",
        "appliances": [
            {"name": "ampoule", "appliance_id": "led_bulb_9w", "quantity": 4, "hours_per_day": 6, "usage_period": "night"},
            {"name": "telephone", "appliance_id": "phone_charger", "quantity": 2, "hours_per_day": 3},
            {"name": "television", "appliance_id": "television_led_24", "quantity": 1, "hours_per_day": 4, "usage_period": "night"},
        ],
    },
    {
        "scenario": "menage_urbain",
        "city": "kinshasa",
        "appliances": [
            {"name": "television", "appliance_id": "television_led_32", "quantity": 1, "hours_per_day": 5, "usage_period": "night"},
            {"name": "congelateur", "appliance_id": "freezer_small", "quantity": 1, "hours_per_day": 24},
            {"name": "ampoule", "appliance_id": "led_bulb_9w", "quantity": 8, "hours_per_day": 6, "usage_period": "night"},
            {"name": "ventilateur", "appliance_id": "fan_table", "quantity": 2, "hours_per_day": 8, "usage_period": "night"},
            {"name": "ordinateur", "appliance_id": "laptop", "quantity": 1, "hours_per_day": 4},
        ],
    },
    {
        "scenario": "boutique_froid",
        "city": "brazzaville",
        "appliances": [
            {"name": "congelateur", "appliance_id": "freezer_small", "quantity": 2, "hours_per_day": 24},
            {"name": "ampoule", "appliance_id": "led_bulb_9w", "quantity": 6, "hours_per_day": 8},
            {"name": "terminal", "appliance_id": "pos_terminal", "quantity": 1, "hours_per_day": 10},
            {"name": "ventilateur", "appliance_id": "fan_ceiling", "quantity": 1, "hours_per_day": 8},
        ],
    },
    {
        "scenario": "salon_coiffure",
        "city": "lubumbashi",
        "appliances": [
            {"name": "tondeuse", "appliance_id": "hair_clipper", "quantity": 2, "hours_per_day": 5},
            {"name": "seche cheveux", "appliance_id": "hair_dryer", "quantity": 1, "hours_per_day": 1},
            {"name": "ampoule", "appliance_id": "led_bulb_9w", "quantity": 8, "hours_per_day": 7},
            {"name": "ventilateur", "appliance_id": "fan_table", "quantity": 2, "hours_per_day": 8},
        ],
    },
    {
        "scenario": "centre_sante",
        "city": "mbandaka",
        "appliances": [
            {"name": "nebuliseur", "appliance_id": "medical_nebulizer", "quantity": 1, "hours_per_day": 3, "essential": True},
            {"name": "refrigerateur", "appliance_id": "fridge_efficient", "quantity": 1, "hours_per_day": 24, "essential": True},
            {"name": "ampoule", "appliance_id": "led_bulb_9w", "quantity": 12, "hours_per_day": 8, "essential": True},
            {"name": "ordinateur", "appliance_id": "laptop", "quantity": 1, "hours_per_day": 6},
        ],
    },
]


def noisy_payload(base: dict, rng: random.Random, index: int) -> dict:
    appliances = []
    for item in base["appliances"]:
        copy = dict(item)
        copy["quantity"] = max(1, int(copy.get("quantity", 1) + rng.choice([-1, 0, 0, 1])))
        copy["hours_per_day"] = round(max(0.5, float(copy.get("hours_per_day", 4)) + rng.uniform(-1.0, 1.0)), 2)
        appliances.append(copy)
    return {
        "customer_id": f"synthetic-customer-{index:06d}",
        "city": base["city"],
        "housing_type": "household" if "menage" in base["scenario"] else "business",
        "people_count": rng.randint(2, 8),
        "autonomy_hours": rng.choice([8, 10, 12, 16, 24]),
        "budget": rng.choice([None, 450000, 900000, 1500000, 2500000]),
        "preference": rng.choice(["economy", "balanced", "performance", "autonomy"]),
        "appliances": appliances,
        "source": "synthetic_dataset",
        "scenario": base["scenario"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Solar Advisor synthetic recommendation dataset.")
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--output", default="data/generated/solar_recommendation_dataset.csv")
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()

    service = SolarAdvisorService()
    rng = random.Random(args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "scenario",
        "customer_id",
        "city",
        "preference",
        "autonomy_hours",
        "appliance_count",
        "total_daily_energy_wh",
        "adjusted_daily_energy_wh",
        "simultaneous_power_w",
        "pv_total_power_w",
        "panel_count",
        "battery_count",
        "battery_usable_capacity_wh",
        "inverter_power_w",
        "estimated_quote_total",
        "risk_budget_insufficient",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(args.rows):
            base = SCENARIOS[index % len(SCENARIOS)]
            payload = noisy_payload(base, rng, index)
            result = service.recommend(payload, save=False)
            quote_total = result["quote"]["total_estimated"]
            writer.writerow(
                {
                    "scenario": payload["scenario"],
                    "customer_id": payload["customer_id"],
                    "city": payload["city"],
                    "preference": payload["preference"],
                    "autonomy_hours": payload["autonomy_hours"],
                    "appliance_count": len(payload["appliances"]),
                    "total_daily_energy_wh": result["consumption"]["total_daily_energy_wh"],
                    "adjusted_daily_energy_wh": result["consumption"]["adjusted_daily_energy_wh"],
                    "simultaneous_power_w": result["consumption"]["simultaneous_power_w"],
                    "pv_total_power_w": result["sizing"]["pv_total_power_w"],
                    "panel_count": result["sizing"]["panel_count"],
                    "battery_count": result["sizing"]["battery_count"],
                    "battery_usable_capacity_wh": result["sizing"]["battery_usable_capacity_wh"],
                    "inverter_power_w": result["sizing"]["inverter_power_w"],
                    "estimated_quote_total": quote_total,
                    "risk_budget_insufficient": bool(payload["budget"] and quote_total > payload["budget"]),
                }
            )
    print(f"Dataset generated: {output} ({args.rows} rows)")


if __name__ == "__main__":
    main()
