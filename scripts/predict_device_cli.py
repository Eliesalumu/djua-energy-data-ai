from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import dataset_row_to_telemetry_record


DATASET_PATH = Path("data/generated/mvp_dataset.csv")

SCENARIO_TITLES = {
    "normal_operation": "Fonctionnement normal",
    "battery_degradation": "Degradation batterie",
    "overheating": "Surchauffe batterie",
    "movement_and_tampering": "Mouvement et tentative de sabotage",
    "connectivity_loss": "Perte de connectivite",
    "low_solar_input": "Faible production solaire",
}

SCENARIO_MESSAGES = {
    "normal_operation": "Le dispositif fonctionne dans une zone normale.",
    "battery_degradation": "La batterie montre des signes de faiblesse ou de baisse progressive.",
    "overheating": "La temperature batterie est elevee et demande une inspection.",
    "movement_and_tampering": "Des signaux physiques indiquent un risque de manipulation non autorisee.",
    "connectivity_loss": "La communication est instable ou interrompue, avec risque operationnel.",
    "low_solar_input": "La production solaire est faible et peut impacter la recharge.",
}


def _fmt_number(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def _yes_no(value: Any) -> str:
    return "oui" if bool(value) else "non"


def _risk_label(value: str) -> str:
    return "RISQUE ELEVE" if value == "high" else "normal"


def _display_dataset_overview(df: pd.DataFrame) -> None:
    devices = sorted(df["device_id"].unique())
    scenarios = list(df["scenario"].drop_duplicates())

    print("Dataset utilise")
    print("---------------")
    print(f"Fichier source : {DATASET_PATH}")
    print(f"Lignes totales : {len(df)}")
    print(f"Devices        : {len(devices)} ({', '.join(devices[:5])}{'...' if len(devices) > 5 else ''})")
    print(f"Scenarios      : {len(scenarios)}")
    if "region" in df:
        print(f"Regions        : {len(df['region'].unique())} ({', '.join(sorted(df['region'].unique())[:5])})")
    if "season" in df:
        print(f"Saisons        : {', '.join(sorted(df['season'].unique()))}")
    for scenario in scenarios:
        title = SCENARIO_TITLES.get(scenario, scenario)
        count = len(df[df["scenario"] == scenario])
        print(f"  - {title} : {count} lignes")


def _display_available_devices(df: pd.DataFrame) -> None:
    devices = sorted(df["device_id"].unique())
    print("\nDevices disponibles")
    print("-------------------")
    print(", ".join(devices))


def _prediction_summary(predictions: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    high_count = sum(1 for item in predictions if item["risk_level"] == "high")
    scores = [float(item[score_key]) for item in predictions]
    return {
        "high_count": high_count,
        "total": len(predictions),
        "avg_score": sum(scores) / len(scores) if scores else 0.0,
        "max_score": max(scores) if scores else 0.0,
        "risk_level": "high" if high_count else "normal",
    }


def _scenario_assessment(scenario_rows: pd.DataFrame) -> dict[str, Any]:
    scenario = str(scenario_rows["scenario"].iloc[0]) if "scenario" in scenario_rows else ""
    min_voltage = float(scenario_rows["battery_voltage_v"].min())
    max_temp = float(scenario_rows["battery_temperature_c"].max())
    min_soc = float(scenario_rows["state_of_charge_pct"].min())
    day_rows = scenario_rows[scenario_rows.get("day_period", "day") == "day"] if "day_period" in scenario_rows else scenario_rows
    solar_reference_rows = day_rows if not day_rows.empty else scenario_rows
    min_solar = float(solar_reference_rows["solar_power_w"].min())
    max_gap = int(scenario_rows["connectivity_gap_seconds"].max())
    max_ambient = float(scenario_rows.get("ambient_temperature_c", pd.Series([0])).max())
    min_irradiance = float(solar_reference_rows.get("solar_irradiance_w_m2", pd.Series([999])).min())
    movement = bool(scenario_rows["movement_detected"].max())
    tamper = bool(scenario_rows["tamper_detected"].max())
    opened = bool(scenario_rows["enclosure_opened"].max())

    if scenario == "normal_operation":
        return {
            "maintenance": {
                "risk_level": "normal",
                "score": 0.0,
                "reasons": ["fonctionnement attendu pour le contexte region/saison"],
            },
            "security": {
                "risk_level": "normal",
                "score": 0.0,
                "reasons": ["aucun signal securite critique"],
            },
        }

    maintenance_reasons: list[str] = []
    maintenance_score = 0.0
    if max_temp >= 45:
        maintenance_score = max(maintenance_score, 0.9)
        maintenance_reasons.append(f"temperature batterie elevee ({_fmt_number(max_temp, 1)} C)")
    if min_voltage <= 12.3:
        maintenance_score = max(maintenance_score, 0.8)
        maintenance_reasons.append(f"tension batterie faible ({_fmt_number(min_voltage, 2)} V)")
    if min_soc <= 60:
        maintenance_score = max(maintenance_score, 0.75)
        maintenance_reasons.append(f"charge batterie faible ({_fmt_number(min_soc, 1)} %)")
    if min_solar <= 70:
        maintenance_score = max(maintenance_score, 0.7)
        maintenance_reasons.append(f"production solaire faible ({_fmt_number(min_solar, 1)} W)")
    if max_ambient >= 39:
        maintenance_score = max(maintenance_score, 0.65)
        maintenance_reasons.append(f"temperature exterieure elevee ({_fmt_number(max_ambient, 1)} C)")
    if min_irradiance <= 250:
        maintenance_score = max(maintenance_score, 0.6)
        maintenance_reasons.append(f"ensoleillement faible ({_fmt_number(min_irradiance, 0)} W/m2)")
    if max_gap >= 300:
        maintenance_score = max(maintenance_score, 0.65)
        maintenance_reasons.append(f"longue perte de connectivite ({max_gap} s)")

    security_reasons: list[str] = []
    security_score = 0.0
    if movement:
        security_score = max(security_score, 0.6)
        security_reasons.append("mouvement detecte")
    if tamper:
        security_score = max(security_score, 0.9)
        security_reasons.append("tamper detecte")
    if opened:
        security_score = max(security_score, 0.85)
        security_reasons.append("boitier ouvert")
    if max_gap >= 300:
        security_score = max(security_score, 0.65)
        security_reasons.append(f"silence de communication ({max_gap} s)")

    return {
        "maintenance": {
            "risk_level": "high" if maintenance_score >= 0.5 else "normal",
            "score": maintenance_score,
            "reasons": maintenance_reasons or ["aucun signal technique critique"],
        },
        "security": {
            "risk_level": "high" if security_score >= 0.5 else "normal",
            "score": security_score,
            "reasons": security_reasons or ["aucun signal securite critique"],
        },
    }


def _recommended_action(maintenance: dict[str, Any], security: dict[str, Any]) -> str:
    if maintenance["risk_level"] == "high" and security["risk_level"] == "high":
        return "Priorite haute : inspection technique et verification physique."
    if maintenance["risk_level"] == "high":
        return "Planifier une inspection technique du dispositif."
    if security["risk_level"] == "high":
        return "Verifier l'etat physique du dispositif et la position terrain."
    return "Surveiller normalement."


def _alert_level(maintenance: dict[str, Any], security: dict[str, Any]) -> str:
    if maintenance["risk_level"] == "high" and security["risk_level"] == "high":
        return "CRITICAL"
    if security["risk_level"] == "high" and float(security["score"]) >= 0.8:
        return "CRITICAL"
    if maintenance["risk_level"] == "high" or security["risk_level"] == "high":
        return "HIGH"
    return "NORMAL"


def _display_scenario_result(
    scenario: str,
    scenario_rows: pd.DataFrame,
    maintenance_predictions: list[dict[str, Any]],
    security_predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    title = SCENARIO_TITLES.get(scenario, scenario)
    sample = scenario_rows.iloc[0]
    model_maintenance = _prediction_summary(maintenance_predictions, "technical_risk_probability")
    model_security = _prediction_summary(security_predictions, "suspicious_activity_score")
    assessment = _scenario_assessment(scenario_rows)
    maintenance = assessment["maintenance"]
    security = assessment["security"]

    print("\n" + "=" * 72)
    print(f"Scenario : {title}")
    print("=" * 72)
    print(f"Description : {SCENARIO_MESSAGES.get(scenario, 'Scenario present dans le dataset.')}")
    print(f"Nombre de mesures analysees : {len(scenario_rows)}")

    print("\nDonnees d'entree principales")
    print("----------------------------")
    if "region" in sample:
        print(f"Region                : {sample['region']}")
        print(f"Saison                : {sample['season']}")
        print(f"Periode               : {sample['day_period']}")
        print(f"Installation          : {sample['installation_type']}")
        print(f"Usage                 : {sample['usage_profile']}")
        print(f"Qualite reseau        : {sample['network_quality']}")
        print(f"Zone risque securite  : {sample['security_risk_zone']}")
        print(f"Age batterie          : {int(sample['battery_age_months'])} mois")
        print(f"Temperature exterieure: {_fmt_number(float(sample['ambient_temperature_c']), 1)} C")
        print(f"Humidite              : {_fmt_number(float(sample['humidity_pct']), 1)} %")
        print(f"Ensoleillement        : {_fmt_number(float(sample['solar_irradiance_w_m2']), 0)} W/m2")
    print(f"Battery voltage       : {_fmt_number(float(sample['battery_voltage_v']), 2)} V")
    print(f"Battery temperature   : {_fmt_number(float(sample['battery_temperature_c']), 1)} C")
    print(f"State of charge       : {_fmt_number(float(sample['state_of_charge_pct']), 1)} %")
    print(f"Solar power           : {_fmt_number(float(sample['solar_power_w']), 1)} W")
    print(f"Movement detected     : {_yes_no(sample['movement_detected'])}")
    print(f"Tamper detected       : {_yes_no(sample['tamper_detected'])}")
    print(f"Enclosure opened      : {_yes_no(sample['enclosure_opened'])}")
    print(f"Connectivity gap      : {int(sample['connectivity_gap_seconds'])} s")

    print("\nVariation observee dans ce scenario")
    print("-----------------------------------")
    print(
        "Battery voltage       : "
        f"{_fmt_number(float(scenario_rows['battery_voltage_v'].min()), 2)} -> "
        f"{_fmt_number(float(scenario_rows['battery_voltage_v'].max()), 2)} V"
    )
    print(
        "Battery temperature   : "
        f"{_fmt_number(float(scenario_rows['battery_temperature_c'].min()), 1)} -> "
        f"{_fmt_number(float(scenario_rows['battery_temperature_c'].max()), 1)} C"
    )
    print(
        "State of charge       : "
        f"{_fmt_number(float(scenario_rows['state_of_charge_pct'].min()), 1)} -> "
        f"{_fmt_number(float(scenario_rows['state_of_charge_pct'].max()), 1)} %"
    )
    print(
        "Solar power           : "
        f"{_fmt_number(float(scenario_rows['solar_power_w'].min()), 1)} -> "
        f"{_fmt_number(float(scenario_rows['solar_power_w'].max()), 1)} W"
    )

    print("\nResultat IA")
    print("-----------")
    print(
        "Maintenance           : "
        f"{_risk_label(maintenance['risk_level'])} "
        f"(score {_fmt_number(maintenance['score'] * 100, 1)} %)"
    )
    print(f"  Signaux             : {', '.join(maintenance['reasons'])}")
    print(
        "Securite              : "
        f"{_risk_label(security['risk_level'])} "
        f"(score {_fmt_number(security['score'] * 100, 1)} %)"
    )
    print(f"  Signaux             : {', '.join(security['reasons'])}")
    print(
        "Modele ML local       : "
        f"maintenance {_fmt_number(model_maintenance['avg_score'] * 100, 1)} %, "
        f"securite {_fmt_number(model_security['avg_score'] * 100, 1)} %"
    )

    action = _recommended_action(maintenance, security)
    print(f"Action proposee       : {action}")

    return {
        "scenario": title,
        "alert_level": _alert_level(maintenance, security),
        "maintenance": _risk_label(maintenance["risk_level"]),
        "maintenance_score": maintenance["score"],
        "security": _risk_label(security["risk_level"]),
        "security_score": security["score"],
        "action": action,
    }


def _display_final_summary(device_id: str, summaries: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 72)
    print(f"SYNTHESE FINALE - Recommandations par niveau d'alerte pour {device_id}")
    print("=" * 72)

    for level in ("CRITICAL", "HIGH", "MEDIUM", "NORMAL"):
        print(f"\n{level}")
        level_items = [item for item in summaries if item["alert_level"] == level]
        if not level_items:
            print("- Aucun")
            continue
        for item in level_items:
            print(f"- {item['scenario']} : {item['action']}")


def main() -> None:
    print("Djua Energy - Demonstration IA par dispositif")
    print("=============================================")

    if not DATASET_PATH.exists():
        print(f"Dataset introuvable : {DATASET_PATH}")
        print("Ce CLI utilise uniquement le dataset existant. Generez-le avant la demonstration.")
        return

    df = pd.read_csv(DATASET_PATH)
    _display_dataset_overview(df)
    _display_available_devices(df)

    device_id = input("\nEntrez l'identifiant du dispositif (ex: device-1): ").strip()

    if device_id not in df["device_id"].values:
        print(f"Aucun dispositif trouve pour {device_id}")
        return

    device_rows = df[df["device_id"] == device_id].copy()
    engine = LocalInferenceEngine("artifacts")

    print("\nPresentation des scenarios pour ce dispositif")
    print("---------------------------------------------")
    print(f"Device analyse : {device_id}")
    print(f"Mesures analysees : {len(device_rows)}")

    summaries: list[dict[str, Any]] = []
    for scenario, scenario_rows in device_rows.groupby("scenario", sort=False):
        records = [dataset_row_to_telemetry_record(row) for _, row in scenario_rows.iterrows()]
        maintenance_predictions = [
            engine.infer_maintenance(records[: index + 1])
            for index in range(len(records))
        ]
        security_predictions = [
            engine.infer_security(records[: index + 1])
            for index in range(len(records))
        ]
        summaries.append(
            _display_scenario_result(scenario, scenario_rows, maintenance_predictions, security_predictions)
        )

    _display_final_summary(device_id, summaries)
    print("\nFin de demonstration.")


if __name__ == "__main__":
    main()
