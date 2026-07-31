from __future__ import annotations

import argparse
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


def _alert_label_fr(value: str) -> str:
    return {
        "CRITICAL": "critique",
        "HIGH": "eleve",
        "MEDIUM": "moyen",
        "NORMAL": "normal",
    }.get(value, value.lower())


def _criticality_rank(level: str) -> int:
    return {"NORMAL": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(level, 0)


def _display_section(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


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
        "scenario_key": scenario,
        "alert_level": _alert_level(maintenance, security),
        "maintenance": _risk_label(maintenance["risk_level"]),
        "maintenance_score": maintenance["score"],
        "maintenance_reasons": maintenance["reasons"],
        "maintenance_model_score": model_maintenance["avg_score"],
        "security": _risk_label(security["risk_level"]),
        "security_score": security["score"],
        "security_reasons": security["reasons"],
        "security_model_score": model_security["avg_score"],
        "action": action,
    }


def _build_scenario_summary(
    scenario: str,
    scenario_rows: pd.DataFrame,
    maintenance_predictions: list[dict[str, Any]],
    security_predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    title = SCENARIO_TITLES.get(scenario, scenario)
    model_maintenance = _prediction_summary(maintenance_predictions, "technical_risk_probability")
    model_security = _prediction_summary(security_predictions, "suspicious_activity_score")
    assessment = _scenario_assessment(scenario_rows)
    maintenance = assessment["maintenance"]
    security = assessment["security"]
    return {
        "scenario": title,
        "scenario_key": scenario,
        "alert_level": _alert_level(maintenance, security),
        "maintenance": _risk_label(maintenance["risk_level"]),
        "maintenance_score": maintenance["score"],
        "maintenance_reasons": maintenance["reasons"],
        "maintenance_model_score": model_maintenance["avg_score"],
        "security": _risk_label(security["risk_level"]),
        "security_score": security["score"],
        "security_reasons": security["reasons"],
        "security_model_score": model_security["avg_score"],
        "action": _recommended_action(maintenance, security),
    }


def _safe_min(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    return float(df[column].min()) if column in df and not df.empty else default


def _safe_max(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    return float(df[column].max()) if column in df and not df.empty else default


def _safe_bool_any(df: pd.DataFrame, column: str) -> bool:
    return bool(df[column].max()) if column in df and not df.empty else False


def _device_indicators(device_rows: pd.DataFrame) -> dict[str, Any]:
    day_rows = device_rows[device_rows.get("day_period", "day") == "day"] if "day_period" in device_rows else device_rows
    solar_rows = day_rows if not day_rows.empty else device_rows
    return {
        "measure_count": len(device_rows),
        "scenario_count": int(device_rows["scenario"].nunique()) if "scenario" in device_rows else 0,
        "min_voltage": _safe_min(device_rows, "battery_voltage_v"),
        "max_temperature": _safe_max(device_rows, "battery_temperature_c"),
        "min_soc": _safe_min(device_rows, "state_of_charge_pct"),
        "min_solar_power": _safe_min(solar_rows, "solar_power_w"),
        "max_connectivity_gap": int(_safe_max(device_rows, "connectivity_gap_seconds")),
        "movement_detected": _safe_bool_any(device_rows, "movement_detected"),
        "tamper_detected": _safe_bool_any(device_rows, "tamper_detected"),
        "enclosure_opened": _safe_bool_any(device_rows, "enclosure_opened"),
        "max_ambient_temperature": _safe_max(device_rows, "ambient_temperature_c"),
        "min_irradiance": _safe_min(solar_rows, "solar_irradiance_w_m2"),
        "max_load_power": _safe_max(device_rows, "load_power_w"),
    }


def _global_alert_level(summaries: list[dict[str, Any]], indicators: dict[str, Any]) -> str:
    levels = [item["alert_level"] for item in summaries]
    level = max(levels, key=_criticality_rank) if levels else "NORMAL"
    if indicators["enclosure_opened"] or indicators["tamper_detected"]:
        return "CRITICAL"
    if indicators["max_temperature"] >= 48 and indicators["min_voltage"] <= 12.3:
        return "CRITICAL"
    return level


def _global_reliability_score(summaries: list[dict[str, Any]], indicators: dict[str, Any]) -> float:
    score = 100.0
    if indicators["enclosure_opened"]:
        score -= 25
    if indicators["tamper_detected"] or indicators["movement_detected"]:
        score -= 18
    if indicators["max_temperature"] >= 45:
        score -= 18
    if indicators["min_voltage"] <= 12.3:
        score -= 14
    if indicators["min_soc"] <= 60:
        score -= 10
    if indicators["max_connectivity_gap"] >= 300:
        score -= 12
    if indicators["min_solar_power"] <= 70:
        score -= 8
    high_scenarios = sum(1 for item in summaries if item["alert_level"] in {"HIGH", "CRITICAL"})
    score -= max(0, high_scenarios - 2) * 3
    if score <= 0 and (indicators["enclosure_opened"] or indicators["max_temperature"] >= 45):
        return 18.0
    return max(0.0, min(100.0, score))


def _issue_sentences(indicators: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if indicators["enclosure_opened"]:
        issues.append({
            "title": "Ouverture du boitier",
            "sentence": (
                "L'IA a detecte que l'enclosure du device a ete ouverte au moins une fois. "
                "Ce signal est critique, car il peut correspondre a une intervention non autorisee, "
                "a une tentative de sabotage ou a une manipulation physique du boitier."
            ),
            "action": (
                "Il faut envoyer un technicien, verifier l'etat du boitier, controler le capteur "
                "d'ouverture, documenter l'intervention et confirmer si l'ouverture etait autorisee."
            ),
        })
    if indicators["tamper_detected"] or indicators["movement_detected"]:
        details = []
        if indicators["movement_detected"]:
            details.append("un mouvement anormal")
        if indicators["tamper_detected"]:
            details.append("un signal de tamper")
        issues.append({
            "title": "Risque securite terrain",
            "sentence": (
                "L'IA a observe " + " et ".join(details) + ". "
                "Le device n'est donc pas seulement en anomalie technique : il presente aussi "
                "un risque securite qui doit etre verifie physiquement."
            ),
            "action": (
                "Il faut verifier la position du kit, controler le verrouillage, regarder les traces "
                "de manipulation et comparer l'evenement avec l'historique client ou technicien."
            ),
        })
    if indicators["max_temperature"] >= 45:
        issues.append({
            "title": "Surchauffe batterie",
            "sentence": (
                f"L'IA a detecte une surchauffe batterie avec un maximum de "
                f"{_fmt_number(indicators['max_temperature'], 1)} C. "
                "Ce niveau de temperature peut accelerer la degradation de la batterie et augmenter "
                "le risque de panne si le device reste en service sans controle."
            ),
            "action": (
                "Il faut inspecter la batterie, verifier la ventilation, controler le regulateur de charge "
                "et eviter une charge prolongee tant que la temperature n'est pas revenue dans une zone normale."
            ),
        })
    if indicators["min_voltage"] <= 12.3 or indicators["min_soc"] <= 60:
        issues.append({
            "title": "Faiblesse batterie",
            "sentence": (
                f"L'IA signale une faiblesse batterie : la tension descend jusqu'a "
                f"{_fmt_number(indicators['min_voltage'], 2)} V et l'etat de charge descend jusqu'a "
                f"{_fmt_number(indicators['min_soc'], 1)} %. "
                "Cela indique que le device peut perdre en autonomie ou tomber en indisponibilite."
            ),
            "action": (
                "Il faut tester la capacite reelle de la batterie, verifier les cycles de charge/decharge "
                "et planifier un remplacement si la degradation se confirme."
            ),
        })
    if indicators["max_connectivity_gap"] >= 300:
        issues.append({
            "title": "Perte de connectivite",
            "sentence": (
                f"L'IA a detecte une perte de connectivite avec un silence maximal de "
                f"{indicators['max_connectivity_gap']} secondes. "
                "Pendant cette periode, la plateforme peut perdre la supervision temps reel du kit."
            ),
            "action": (
                "Il faut verifier le signal reseau, la carte SIM, l'antenne et la file de messages en attente "
                "pour retablir une remontee fiable des donnees."
            ),
        })
    if indicators["min_solar_power"] <= 70:
        issues.append({
            "title": "Production solaire faible",
            "sentence": (
                f"L'IA observe une production solaire basse, avec un minimum de "
                f"{_fmt_number(indicators['min_solar_power'], 1)} W sur les mesures de jour disponibles. "
                "Cette situation peut expliquer une recharge insuffisante et aggraver les problemes batterie."
            ),
            "action": (
                "Il faut nettoyer ou repositionner le panneau, verifier le cablage solaire et controler "
                "le regulateur de charge."
            ),
        })
    if not issues:
        issues.append({
            "title": "Etat normal",
            "sentence": (
                "L'IA ne detecte pas de signal critique sur ce device. Les mesures techniques, "
                "securite, connectivite et production solaire restent compatibles avec une surveillance normale."
            ),
            "action": "Il faut continuer la supervision standard sans intervention terrain immediate.",
        })
    return issues


def _display_variables_analyzed(device_rows: pd.DataFrame) -> None:
    sample = device_rows.iloc[0]
    _display_section("Variables analysees par l'IA")
    print(
        "Contexte terrain      : "
        f"region={sample.get('region', 'n/a')}, saison={sample.get('season', 'n/a')}, "
        f"installation={sample.get('installation_type', 'n/a')}, usage={sample.get('usage_profile', 'n/a')}, "
        f"zone securite={sample.get('security_risk_zone', 'n/a')}."
    )
    print(
        "Batterie              : tension, temperature, etat de charge, age batterie, "
        "puissance batterie et tendance sur la fenetre de mesures."
    )
    print(
        "Solaire               : puissance solaire, irradiance, periode jour/nuit et capacite de recharge."
    )
    print(
        "Securite physique     : mouvement detecte, tamper detecte, enclosure opened, distance et precision GPS."
    )
    print(
        "Connectivite          : qualite reseau, statut connexion, signal, pertes de communication et gap maximum."
    )
    print(
        "Charge et environnement: consommation, temperature exterieure, humidite et profil d'utilisation."
    )


def _display_global_diagnosis(
    device_id: str,
    device_rows: pd.DataFrame,
    summaries: list[dict[str, Any]],
) -> None:
    indicators = _device_indicators(device_rows)
    level = _global_alert_level(summaries, indicators)
    sample = device_rows.iloc[0]
    critical_or_high = [
        item for item in summaries if item["alert_level"] in {"CRITICAL", "HIGH"}
    ]
    sorted_summaries = sorted(
        summaries,
        key=lambda item: (
            _criticality_rank(item["alert_level"]),
            float(item["maintenance_score"]) + float(item["security_score"]),
        ),
        reverse=True,
    )
    detected_cases = [
        item["scenario"]
        for item in sorted_summaries
        if item["alert_level"] in {"CRITICAL", "HIGH"}
    ]

    print("\n" + "=" * 78)
    print(f"DIAGNOSTIC IA GLOBAL DU DEVICE {device_id}")
    print("=" * 78)

    if not critical_or_high:
        print(
            f"Ce device {device_id} est dans un etat normal. L'IA n'a pas detecte de probleme critique "
            f"sur les {indicators['measure_count']} mesures analysees. La surveillance standard peut continuer."
        )
        _display_section("Decision recommandee")
        print("Decision IA : continuer la supervision normale du device.")
        return

    problems = ", ".join(detected_cases)
    security_part = ""
    if indicators["enclosure_opened"] or indicators["tamper_detected"] or indicators["movement_detected"]:
        security_details = []
        if indicators["enclosure_opened"]:
            security_details.append("ouverture du boitier detectee")
        if indicators["tamper_detected"]:
            security_details.append("tamper detecte")
        if indicators["movement_detected"]:
            security_details.append("mouvement anormal detecte")
        security_part = " Sur le plan securite, " + ", ".join(security_details) + "."

    print(
        f"Ce device {device_id} est dans un etat {_alert_label_fr(level)}. "
        f"L'IA a analyse {indicators['measure_count']} mesures et detecte les cas suivants : {problems}. "
        f"La perte de connectivite atteint jusqu'a {indicators['max_connectivity_gap']} secondes. "
        f"La batterie, agee de {int(sample.get('battery_age_months', 0))} mois, presente une surchauffe "
        f"jusqu'a {_fmt_number(indicators['max_temperature'], 1)} C, une tension qui descend jusqu'a "
        f"{_fmt_number(indicators['min_voltage'], 2)} V et un niveau de charge minimum de "
        f"{_fmt_number(indicators['min_soc'], 1)} %. "
        f"La production solaire descend jusqu'a {_fmt_number(indicators['min_solar_power'], 1)} W, "
        f"ce qui peut aggraver la degradation batterie et l'autonomie du device."
        f"{security_part}"
    )

    actions = [
        "ouvrir une intervention prioritaire",
        "verifier physiquement le boitier et confirmer si l'ouverture etait autorisee",
        "controler la batterie, la ventilation et le regulateur de charge",
        "verifier le panneau solaire, le cablage et la qualite de recharge",
        "retablir la connectivite en controlant le signal reseau, la SIM et l'antenne",
    ]
    print("\nAction IA : " + "; ".join(actions) + ".")


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demonstration CLI des predictions IA pour un dispositif Djua Energy."
    )
    parser.add_argument(
        "--device",
        help="Identifiant du dispositif a analyser, par exemple device-2.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Afficher aussi le detail technique scenario par scenario.",
    )
    parser.add_argument(
        "--jury",
        action="store_true",
        help="Afficher une sortie concentree pour la demonstration jury.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Analyser un seul device puis terminer le script.",
    )
    return parser.parse_args()


def _analyze_device(
    device_id: str,
    df: pd.DataFrame,
    engine: LocalInferenceEngine,
    *,
    details: bool = False,
) -> bool:
    if device_id not in df["device_id"].values:
        print(f"Aucun dispositif trouve pour {device_id}")
        return False

    device_rows = df[df["device_id"] == device_id].copy()

    print("\nAnalyse du dispositif")
    print("---------------------")
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
        if details:
            summaries.append(
                _display_scenario_result(scenario, scenario_rows, maintenance_predictions, security_predictions)
            )
        else:
            summaries.append(
                _build_scenario_summary(scenario, scenario_rows, maintenance_predictions, security_predictions)
            )

    _display_global_diagnosis(device_id, device_rows, summaries)
    if details:
        _display_final_summary(device_id, summaries)
    return True


def main() -> None:
    args = _parse_args()
    print("Djua Energy - Demonstration IA par dispositif")
    print("=============================================")

    if not DATASET_PATH.exists():
        print(f"Dataset introuvable : {DATASET_PATH}")
        print("Ce CLI utilise uniquement le dataset existant. Generez-le avant la demonstration.")
        return

    df = pd.read_csv(DATASET_PATH)
    engine = LocalInferenceEngine("artifacts")
    if not args.jury:
        _display_dataset_overview(df)
        _display_available_devices(df)

    first_device_id = args.device or input("\nEntrez l'identifiant du dispositif (ex: device-2): ").strip()
    _analyze_device(first_device_id, df, engine, details=args.details)

    if args.once or args.details:
        print("\nFin de demonstration.")
        return

    while True:
        next_device_id = input("\nEntrez un autre device a analyser, ou tapez q pour quitter: ").strip()
        if next_device_id.lower() in {"q", "quit", "exit"}:
            break
        if not next_device_id:
            continue
        _analyze_device(next_device_id, df, engine, details=False)

    print("\nFin de demonstration.")


if __name__ == "__main__":
    main()
