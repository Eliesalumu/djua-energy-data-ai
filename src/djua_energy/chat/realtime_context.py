"""Contexts built exclusively from persisted telemetry and predictions, never demo CSVs."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

FIELDS = (
    "event_time", "battery_voltage_v", "battery_current_a", "state_of_charge_pct",
    "state_of_health_pct", "solar_power_w", "energy_generated_wh", "load_power_w",
    "energy_consumed_wh", "connection_status", "connectivity_gap_seconds",
    "solar_error_code", "day_period",
    "tamper_detected", "enclosure_opened", "movement_detected", "device_temperature_c",
)
LEVELS = {"none": "normal", "low": "normal", "normal": "normal", "medium": "elevated",
          "high": "elevated", "elevated": "elevated", "critical": "critical"}


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def build_realtime_kit_context(store, device_id: str) -> dict:
    state = store.get_device_state(device_id)
    history = store.recent_records_for_device(device_id, limit=24)
    latest = history[-1] if history else (state or {}).get("latest_payload", {})
    predictions = store.prediction_history(device_id, limit=5)
    prediction = predictions[0] if predictions else (state or {}).get("latest_prediction")
    observed = {field: latest[field] for field in FIELDS if field in latest}
    raw_records = history or ([latest] if latest else [])
    source_labels = sorted({str(row.get("source", "unspecified")) for row in raw_records})
    synthetic = any(row.get("scenario") or "simulat" in str(row.get("source", "")).lower()
                    or "synthetic" in str(row.get("source", "")).lower() for row in raw_records)
    level = LEVELS.get((state or {}).get("risk_level", ""), "unknown")
    connection = latest.get("connection_status")
    maintenance = (prediction or {}).get("maintenance_prediction", {})
    security = (prediction or {}).get("security_prediction", {})
    alert = (prediction or {}).get("alert", {})
    maintenance_problem = maintenance.get("risk_level") in {"medium", "high", "critical", "eleve", "critique"} or alert.get("maintenance_priority") in {"medium", "high", "critical"}
    factors = str(maintenance.get("main_factors", [])).lower()
    battery_problem = maintenance_problem and ("battery" in factors or "batterie" in factors)
    soc = observed.get("state_of_charge_pct")
    if _numeric(soc) and soc < 20:
        battery_problem = True
    security_problem = any(latest.get(key) is True for key in ("tamper_detected", "enclosure_opened", "movement_detected"))
    security_problem |= security.get("risk_level") in {"medium", "high", "critical", "eleve", "critique"}
    security_problem |= alert.get("security_priority") in {"medium", "high", "critical"}
    production_problem = latest.get("solar_error_code") not in (None, "", "NONE", "none", "0", 0)
    trend = None
    comparable = [r for r in history if _numeric(r.get("solar_power_w")) and r.get("day_period") == latest.get("day_period")]
    if len(comparable) >= 2:
        trend = {"first_power_w": comparable[0]["solar_power_w"], "last_power_w": comparable[-1]["solar_power_w"],
                 "difference_w": round(comparable[-1]["solar_power_w"] - comparable[0]["solar_power_w"], 2),
                 "cause": "Non determinable a partir de cette variation seule."}
    return {
        "device_id": device_id, "kit_id": latest.get("kit_id") or (state or {}).get("kit_id"),
        "found": bool(latest or state), "source": "RealtimeTelemetryStore",
        "telemetry_available": any(value is not None for field, value in observed.items() if field != "event_time"),
        "provenance": {"synthetic_or_simulated": synthetic, "labels": source_labels,
                       "notice": "Mesures stockees, origine physique non verifiee." if not synthetic else "Donnees de simulation : ne pas les presenter comme des mesures terrain reelles."},
        "observed": observed, "predictions": prediction, "risk_level": level,
        "last_observation_at": latest.get("event_time") or (state or {}).get("last_event_time"),
        "last_prediction_at": (prediction or {}).get("predicted_at"),
        "recent_history": [{key: r[key] for key in FIELDS if key in r} for r in history],
        "prediction_history": [{"predicted_at": p["predicted_at"], "risk_level": p["risk_level"],
                                "recommended_action": p.get("recommended_action")} for p in predictions],
        "production_variation": trend,
        "recommended_action": (state or {}).get("recommended_action") or (prediction or {}).get("recommended_action"),
        "flags": {"battery": battery_problem, "security": security_problem, "production": production_problem,
                  "connectivity": connection in {"disconnected", "offline"},
                  "maintenance": maintenance_problem},
        "coverage": {"battery": bool(maintenance) or _numeric(soc),
                     "security": bool(security) or any(key in latest for key in ("tamper_detected", "enclosure_opened", "movement_detected")),
                     "production": "solar_error_code" in latest,
                     "connectivity": connection is not None, "maintenance": bool(maintenance)},
        "activity": "inactive" if connection in {"disconnected", "offline"} else "active" if connection in {"connected", "online"} else "unknown",
        "missing_data": [field for field in FIELDS if field not in observed]
                        + ([] if prediction else ["predictions"]) + ([] if trend else ["production_variation"]),
    }


def build_realtime_fleet_context(store, device_ids: list[str], topic: str = "general") -> dict:
    kits = [build_realtime_kit_context(store, device_id) for device_id in sorted(set(device_ids))]
    available = [kit for kit in kits if kit["found"]]
    risk_counts = Counter(kit["risk_level"] for kit in available)
    activity_counts = Counter(kit["activity"] for kit in available)
    priorities = sorted(available, key=lambda k: ({"critical": 3, "elevated": 2, "unknown": 1, "normal": 0}[k["risk_level"]],
                                               (k["predictions"] or {}).get("risk_score", 0)), reverse=True)
    matching = [kit for kit in priorities if topic not in kit["flags"] or kit["flags"][topic]]
    return {
        "source": "RealtimeTelemetryStore", "generated_at": datetime.now(UTC).isoformat(),
        "scope_device_count": len(kits), "device_count": len(available),
        "telemetry_available": any(kit["telemetry_available"] for kit in kits),
        "kit_count": len({k["kit_id"] for k in available if k["kit_id"]}),
        "devices_without_kit_id": sum(not k["kit_id"] for k in available),
        "risk_counts": {level: risk_counts[level] for level in ("normal", "elevated", "critical", "unknown")},
        "activity_counts": {level: activity_counts[level] for level in ("active", "inactive", "unknown")},
        "alerts": {name: sum(k["flags"][name] for k in available) for name in ("maintenance", "security", "connectivity", "battery", "production")},
        "alert_data_unavailable": {name: sum(not k["coverage"][name] for k in available)
                                   for name in ("maintenance", "security", "connectivity", "battery", "production")},
        "criteria": {"battery": "Facteur batterie dans une prediction de maintenance a risque ou SOC observe < 20%.",
                     "production": "Code erreur solaire observe non NONE.", "activity": "Uniquement connection_status observe; sinon unknown.",
                     "risk": "Dernier niveau predit stocke; aucune nouvelle inference."},
        "matching_count": len(matching), "topic": topic,
        "devices": [{key: kit[key] for key in ("device_id", "kit_id", "risk_level", "flags", "observed", "last_observation_at", "recommended_action", "provenance")}
                    for kit in matching[:10]],
        "priority_interventions": [{"device_id": k["device_id"], "risk_level": k["risk_level"], "action": k["recommended_action"]}
                                   for k in priorities if k["risk_level"] in {"critical", "elevated"}][:10],
        "devices_without_data": [k["device_id"] for k in kits if not k["found"]],
        "missing_data": ["Cause certaine des anomalies", "Etat des interventions terrain", "Validation de l'origine physique des mesures"],
    }


def realtime_fallback(context: dict) -> str:
    if "device_count" in context:
        if not context["device_count"]:
            return "Aucune mesure ni prediction disponible dans votre perimetre. Impossible de calculer la situation du parc."
        counts = context["risk_counts"]
        lines = [f"Perimetre consulte : {context['device_count']} devices, {context['kit_count']} kits identifies.",
                 f"Normaux : {counts['normal']}; eleves : {counts['elevated']}; critiques : {counts['critical']}; risque inconnu : {counts['unknown']}.",
                 "Alertes calculees : " + ", ".join(f"{k}={v}" for k, v in context["alerts"].items()) + "."]
        lines += [f"{k['device_id']} : {k['risk_level']}. Action : {k['recommended_action'] or 'Aucune action enregistree.'}" for k in context["devices"]]
        if any(k["provenance"]["synthetic_or_simulated"] for k in context["devices"]):
            lines.append("Attention : des donnees de simulation sont presentes.")
        lines.append("Causes certaines et suivi des interventions indisponibles.")
        lines.append("Devices sans donnees pour chaque indicateur : " + str(context["alert_data_unavailable"]))
        if context["devices_without_data"]:
            lines.append("Aucune mesure pour : " + ", ".join(context["devices_without_data"][:10]))
        return "\n".join(lines)
    kit = context["kit"]
    if not kit["found"]:
        return f"Aucune mesure ni prediction disponible pour {kit['device_id']}."
    labels = {"battery": ("state_of_charge_pct", "battery_voltage_v", "state_of_health_pct"),
              "production": ("solar_power_w", "energy_generated_wh"),
              "consumption": ("load_power_w", "energy_consumed_wh"),
              "connectivity": ("connection_status", "connectivity_gap_seconds"),
              "security": ("tamper_detected", "enclosure_opened", "movement_detected")}
    fields = labels.get(context.get("topic"), ("state_of_charge_pct", "solar_power_w", "connection_status"))
    names = {"state_of_charge_pct": ("Charge batterie", "%"), "battery_voltage_v": ("Tension batterie", "V"),
             "state_of_health_pct": ("Sante batterie", "%"), "solar_power_w": ("Puissance solaire", "W"),
             "energy_generated_wh": ("Energie produite", "Wh"), "load_power_w": ("Puissance consommee", "W"),
             "energy_consumed_wh": ("Energie consommee", "Wh"), "connection_status": ("Connexion", ""),
             "connectivity_gap_seconds": ("Coupure de connexion", "secondes"),
             "tamper_detected": ("Sabotage detecte", ""), "enclosure_opened": ("Boitier ouvert", ""),
             "movement_detected": ("Mouvement detecte", "")}
    details = "; ".join(f"{names[key][0]} : {kit['observed'][key]} {names[key][1]}".strip()
                        for key in fields if key in kit["observed"]) or "Mesures demandees indisponibles."
    lines = [f"{kit['device_id']} : dernier risque predit {kit['risk_level']}.", details,
             f"Derniere observation : {kit['last_observation_at'] or 'date indisponible'}.",
             f"Action recommandee : {kit['recommended_action'] or 'Aucune action enregistree; demander un diagnostic au support.'}"]
    if context.get("topic") == "production":
        lines.append(f"Variation recente : {kit['production_variation']}. Cause certaine indisponible.")
    if context.get("topic") == "history":
        lines.append(f"Historique disponible : {len(kit['recent_history'])} mesures, {len(kit['prediction_history'])} predictions.")
        lines += [str(row) for row in kit["recent_history"][-3:]]
    if context.get("topic") in {"predictions", "maintenance"} or context.get("access", {}).get("role") == "technician":
        prediction = kit["predictions"] or {}
        lines.append("Predictions stockees : " + str({key: prediction.get(key, "indisponible")
                                                    for key in ("maintenance_probability", "security_probability", "predicted_at")}))
    if kit["provenance"]["synthetic_or_simulated"]:
        lines.append("Donnees de simulation, pas des mesures terrain verifiees.")
    return "\n".join(lines)
