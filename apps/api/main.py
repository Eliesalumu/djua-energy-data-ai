"""API FastAPI DJUA ENERGY.

Les endpoints frontend sont declares dans ce fichier.
Chercher `@app.get("/frontend/command-center")` pour le Command Center.

Routes frontend actuellement disponibles :
- GET /frontend/command-center
- GET /frontend/fleet
- GET /frontend/decisions/{decision_id}
- GET /frontend/kits/{kit_id}/digital-twin
- GET /frontend/interventions/create
- GET /frontend/customers/{client_id}/risk-profile
- GET /frontend/performance
- GET /frontend/admin/data-ai
- GET /frontend/realtime/events
"""

from datetime import UTC, datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from djua_energy.alerting.service import build_alert_decision
from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.contracts import validate_payload
from djua_energy.pipeline.features import build_maintenance_features, build_security_features
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService
from djua_energy.chat.service import DjuaChatService
from djua_energy.database.realtime_store import RealtimeTelemetryStore

app = FastAPI(title="Djua Energy IoT Demo", version="0.1.0")
engine = LocalInferenceEngine("artifacts")
realtime_store = RealtimeTelemetryStore()
telemetry_service = TelemetryIngestionService(engine, realtime_store=realtime_store)
chat_service = DjuaChatService(engine=engine)


class TelemetryWindowRequest(BaseModel):
    records: list[dict] = Field(default_factory=list)


class AiChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


DEMO_NOW = "2026-07-20T09:31:00Z"


def _metric(
    metric_id: str,
    label: str,
    value: float | int,
    unit: str,
    previous_value: float | int,
    trend: str,
    state: str,
    period: str = "today",
) -> dict:
    variation_abs = round(float(value) - float(previous_value), 2)
    variation_pct = round((variation_abs / float(previous_value)) * 100, 2) if previous_value else 0.0
    return {
        "id": metric_id,
        "label": label,
        "value": value,
        "unit": unit,
        "period": period,
        "previous_value": previous_value,
        "variation_absolute": variation_abs,
        "variation_percent": variation_pct,
        "trend": trend,
        "state": state,
        "last_updated_at": DEMO_NOW,
        "freshness": {"label": "Mis a jour il y a 2 minutes", "age_seconds": 120},
        "sparkline": [previous_value, round((previous_value + value) / 2, 2), value],
    }


def _source(kind: str, detail: str, model_name: str | None = None) -> dict:
    return {
        "kind": kind,
        "detail": detail,
        "model_name": model_name,
        "generated_at": DEMO_NOW,
    }


def _demo_windows() -> dict[str, list[dict]]:
    scenarios_by_kit = {
        "kit-0": "movement_then_connectivity_loss",
        "kit-1": "battery_overheating",
        "kit-2": "normal_operation",
    }
    records = SyntheticTelemetryGenerator(seed=31, num_kits=3).generate(
        scenarios=sorted(set(scenarios_by_kit.values())),
        duration_hours=3,
    )
    windows: dict[str, list[dict]] = {}
    for record in records:
        kit_id = str(record["kit_id"])
        if scenarios_by_kit.get(kit_id) == record.get("scenario"):
            windows.setdefault(kit_id, []).append(record)
    return windows


def _model_score(maintenance_prediction: dict, security_prediction: dict) -> int:
    maintenance_score = float(maintenance_prediction["technical_risk_probability"])
    security_score = float(security_prediction["suspicious_activity_score"])
    return round(max(maintenance_score, security_score) * 100)


def _severity_from_alert(priority: str) -> str:
    return "low" if priority == "none" else priority


def _decision_category(maintenance_prediction: dict, security_prediction: dict) -> str:
    maintenance_score = float(maintenance_prediction["technical_risk_probability"])
    security_score = float(security_prediction["suspicious_activity_score"])
    return "security" if security_score >= maintenance_score else "maintenance"


def _human_label_for_category(category: str) -> dict[str, str]:
    if category == "security":
        return {
            "title": "Suspicion de fraude",
            "type": "fraud_detection",
            "summary": "Le modele securite signale un comportement compatible avec une manipulation, un deplacement ou une perte de controle.",
            "recommendation": "Verifier le boitier, la position GPS et l'identite terrain.",
        }
    return {
        "title": "Prediction de maintenance",
        "type": "predictive_maintenance",
        "summary": "Le modele maintenance signale un risque technique sur le kit.",
        "recommendation": "Planifier une inspection technique preventive.",
    }


def _feature_snapshot(records: list[dict]) -> dict:
    maintenance_features = build_maintenance_features(records).iloc[-1].to_dict()
    security_features = build_security_features(records).iloc[-1].to_dict()
    selected = {
        "maintenance": {
            "battery_voltage_trend": round(float(maintenance_features.get("battery_voltage_trend", 0)), 3),
            "battery_temp_trend": round(float(maintenance_features.get("battery_temp_trend", 0)), 3),
            "max_battery_temp": round(float(maintenance_features.get("max_battery_temp", 0)), 3),
            "connectivity_gap": round(float(maintenance_features.get("connectivity_gap", 0)), 3),
            "solar_load_ratio": round(float(maintenance_features.get("solar_load_ratio", 0)), 3),
            "battery_age_months": round(float(maintenance_features.get("battery_age_months", 0)), 3),
        },
        "security": {
            "distance_to_installation": round(float(security_features.get("distance_to_installation", 0)), 3),
            "geofence_exit": round(float(security_features.get("geofence_exit", 0)), 3),
            "movement_then_gap": round(float(security_features.get("movement_then_gap", 0)), 3),
            "device_silence_duration": round(float(security_features.get("device_silence_duration", 0)), 3),
            "enclosure_opened": round(float(security_features.get("enclosure_opened", 0)), 3),
            "tamper_events": round(float(security_features.get("tamper_events", 0)), 3),
        },
    }
    return selected


def _score_history(records: list[dict]) -> list[dict]:
    history = []
    for index in range(1, len(records) + 1):
        window = records[:index]
        maintenance_prediction = engine.infer_maintenance(window)
        security_prediction = engine.infer_security(window)
        history.append({
            "timestamp": window[-1]["event_time"],
            "score": _model_score(maintenance_prediction, security_prediction),
            "maintenance_probability": maintenance_prediction["technical_risk_probability"],
            "security_probability": security_prediction["suspicious_activity_score"],
            "source": _source("model_output", "Score recalcule par les modeles maintenance et securite.", "LocalInferenceEngine"),
        })
    return history


def _risk_factors(records: list[dict], decision: dict) -> list[dict]:
    latest = records[-1]
    features = decision["feature_snapshot"]
    return [
        {
            "name": "technical_risk_probability",
            "label": "Probabilite de risque technique",
            "description": "Sortie directe du modele maintenance.",
            "observed_value": decision["model_outputs"]["maintenance"]["technical_risk_probability"],
            "expected_value": 0.65,
            "delta": round(float(decision["model_outputs"]["maintenance"]["technical_risk_probability"]) - 0.65, 3),
            "unit": "probability",
            "contribution": None,
            "importance_relative": "model_top_factor" if decision["category"] == "maintenance" else "supporting_signal",
            "direction": "increases_risk",
            "severity": decision["severity"],
            "category": "maintenance",
            "source": _source("model_output", "Probabilite retournee par infer_maintenance.", "maintenance"),
            "measured_at": DEMO_NOW,
        },
        {
            "name": "suspicious_activity_score",
            "label": "Score d'activite suspecte",
            "description": "Sortie directe du modele securite.",
            "observed_value": decision["model_outputs"]["security"]["suspicious_activity_score"],
            "expected_value": 0.65,
            "delta": round(float(decision["model_outputs"]["security"]["suspicious_activity_score"]) - 0.65, 3),
            "unit": "probability",
            "contribution": None,
            "importance_relative": "model_top_factor" if decision["category"] == "security" else "supporting_signal",
            "direction": "increases_risk",
            "severity": decision["severity"],
            "category": "security",
            "source": _source("model_output", "Score retourne par infer_security.", "security"),
            "measured_at": DEMO_NOW,
        },
        {
            "name": "connectivity_gap",
            "label": "Duree sans communication",
            "description": "Feature fournie au modele et calculee depuis la telemetrie.",
            "observed_value": features["maintenance"]["connectivity_gap"],
            "expected_value": 60,
            "delta": round(features["maintenance"]["connectivity_gap"] - 60, 3),
            "unit": "seconds",
            "contribution": None,
            "importance_relative": "explanatory_feature",
            "direction": "increases_risk",
            "severity": "high" if features["maintenance"]["connectivity_gap"] >= 300 else "low",
            "category": "connectivity",
            "source": _source("model_feature", "Feature presente dans le vecteur d'entree du modele.", "maintenance/security"),
            "measured_at": latest["event_time"],
        },
        {
            "name": "max_battery_temp",
            "label": "Temperature batterie maximale",
            "description": "Feature maintenance calculee sur la fenetre de telemetrie.",
            "observed_value": features["maintenance"]["max_battery_temp"],
            "expected_value": 40,
            "delta": round(features["maintenance"]["max_battery_temp"] - 40, 3),
            "unit": "celsius",
            "contribution": None,
            "importance_relative": "explanatory_feature",
            "direction": "increases_risk",
            "severity": "high" if features["maintenance"]["max_battery_temp"] >= 44 else "low",
            "category": "battery",
            "source": _source("model_feature", "Feature presente dans le vecteur d'entree du modele maintenance.", "maintenance"),
            "measured_at": latest["event_time"],
        },
        {
            "name": "movement_then_gap",
            "label": "Mouvement suivi d'une perte de connexion",
            "description": "Feature securite calculee avant inference.",
            "observed_value": features["security"]["movement_then_gap"],
            "expected_value": 0,
            "delta": features["security"]["movement_then_gap"],
            "unit": "binary",
            "contribution": None,
            "importance_relative": "explanatory_feature",
            "direction": "increases_risk",
            "severity": "high" if features["security"]["movement_then_gap"] else "low",
            "category": "security",
            "source": _source("model_feature", "Feature presente dans le vecteur d'entree du modele securite.", "security"),
            "measured_at": latest["event_time"],
        },
    ]


def _demo_entities() -> dict:
    windows = _demo_windows()

    kits = []
    alerts = []
    decisions = []
    interventions = []
    customers = []
    model_runs = []
    all_records = []
    for index, (kit_id, records) in enumerate(sorted(windows.items()), start=1):
        record = records[-1]
        maintenance_prediction = engine.infer_maintenance(records)
        security_prediction = engine.infer_security(records)
        alert_decision = build_alert_decision(
            device_id=str(record["device_id"]),
            maintenance_prediction=maintenance_prediction,
            security_prediction=security_prediction,
        )
        score = _model_score(maintenance_prediction, security_prediction)
        severity = _severity_from_alert(alert_decision.priority)
        category = _decision_category(maintenance_prediction, security_prediction)
        labels = _human_label_for_category(category)
        feature_snapshot = _feature_snapshot(records)
        client_id = f"client-{index:03d}"
        decision_id = f"decision-{index:03d}"
        alert_id = f"alert-{index:03d}"
        intervention_id = f"intervention-{index:03d}"
        health_score = max(0, 100 - score)
        status = "offline" if record.get("connection_status") == "disconnected" else "operational"
        model_run_id = f"model-run-{index:03d}"
        all_records.extend(records)
        model_runs.append({
            "model_run_id": model_run_id,
            "kit_id": kit_id,
            "device_id": record["device_id"],
            "records_used": len(records),
            "window_started_at": records[0]["event_time"],
            "window_ended_at": record["event_time"],
            "maintenance_model_version": maintenance_prediction["model_version"],
            "security_model_version": security_prediction["model_version"],
            "source": _source("model_output", "Execution reelle de LocalInferenceEngine sur une fenetre de telemetrie.", "LocalInferenceEngine"),
        })

        kit = {
            "kit_id": kit_id,
            "device_id": record["device_id"],
            "serial_number": record["serial_number"],
            "model": record.get("device_model", "djua-solar-v1"),
            "installation_type": record.get("installation_type"),
            "client_id": client_id,
            "client_name": f"Client demonstration {index}",
            "region": record.get("region"),
            "city": "Zone pilote",
            "country": "CI",
            "status": status,
            "connectivity_status": record.get("connection_status"),
            "health_score": health_score,
            "risk_level": severity,
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "gps_accuracy_m": record.get("gps_accuracy_m"),
            "last_telemetry_at": record["event_time"],
            "last_movement_at": record["event_time"] if record.get("movement_detected") else None,
            "active_alert_id": alert_id if severity != "low" else None,
            "active_intervention_id": intervention_id if severity in {"critical", "high"} else None,
            "model_score": score,
            "model_outputs": {
                "maintenance": maintenance_prediction,
                "security": security_prediction,
            },
            "source": _source("model_derived", "Statut de risque derive des sorties maintenance/security et de la priorisation d'alerte.", "LocalInferenceEngine"),
        }
        kits.append(kit)

        if severity != "low":
            alerts.append({
                "alert_id": alert_id,
                "decision_id": decision_id,
                "type": labels["type"],
                "title": labels["title"],
                "summary": labels["summary"],
                "severity": severity,
                "kit": {"kit_id": kit_id, "label": record["serial_number"]},
                "client": {"client_id": client_id, "name": f"Client demonstration {index}"},
                "location": {"country": "CI", "region": record.get("region"), "city": "Zone pilote"},
                "created_at": record["event_time"],
                "age_label": "2 min",
                "status": "open",
                "review_status": "pending_review",
                "assignee": "operations",
                "recommended_action": alert_decision.recommended_action,
                "is_new": True,
                "model_run_id": model_run_id,
                "source": _source("model_derived", "Alerte creee depuis build_alert_decision apres inference modele.", "LocalInferenceEngine"),
            })

        decisions.append({
            "decision_id": decision_id,
            "title": labels["title"],
            "category": category,
            "type": labels["type"],
            "severity": severity,
            "status": "open" if severity != "low" else "monitoring",
            "created_at": record["event_time"],
            "updated_at": record["event_time"],
            "kit_id": kit_id,
            "client_id": client_id,
            "region": record.get("region"),
            "model": {
                "name": "LocalInferenceEngine",
                "maintenance_version": maintenance_prediction["model_version"],
                "security_version": security_prediction["model_version"],
                "run_id": model_run_id,
            },
            "score": score,
            "probability": round(score / 100, 3),
            "confidence": 0.82,
            "predicted_class": severity,
            "threshold": 0.65,
            "summary": labels["summary"],
            "primary_recommendation": labels["recommendation"],
            "human_review": {"status": "pending", "required": severity != "low"},
            "model_outputs": {
                "maintenance": maintenance_prediction,
                "security": security_prediction,
                "alert_priority": alert_decision.__dict__,
            },
            "feature_snapshot": feature_snapshot,
            "source": _source("model_output", "Decision construite depuis les sorties directes des deux modeles locaux.", "LocalInferenceEngine"),
        })

        interventions.append({
            "intervention_id": intervention_id,
            "decision_id": decision_id,
            "kit_id": kit_id,
            "recommended_type": "fraud_check" if category == "security" else "preventive_maintenance",
            "priority": severity,
            "urgency": "same_day" if severity == "critical" else ("this_week" if severity == "high" else "monitoring"),
            "justification": f"Recommandation derivee du score modele {score}% et de la priorite {alert_decision.priority}.",
            "estimated_duration_minutes": 90 if category == "security" else 45,
            "estimated_cost": {"amount": 42 if category == "security" else 18, "currency": "EUR", "method": "demo_assumption_not_model_output"},
            "required_skills": ["diagnostic_iot", "controle_gps"] if category == "security" else ["maintenance_batterie"],
            "checklist": ["Verifier l'identite du kit", "Controler le boitier", "Comparer la position attendue"],
            "confidence": 0.8,
            "source": _source("model_derived", "Type et priorite derives de la decision IA; cout et duree sont des hypotheses demo.", "LocalInferenceEngine"),
        })

        customers.append({
            "client_id": client_id,
            "name": f"Client demonstration {index}",
            "risk_score": score,
            "risk_level": severity,
            "trend": "up" if severity != "low" else "stable",
            "model_version": "derived-from-kit-models",
            "confidence": 0.78,
            "summary": "Risque client derive du risque IA du kit rattache.",
            "main_factors": ["kit_model_score", "maintenance_prediction", "security_prediction"],
            "recommendations": ["Contacter le client", "Verifier la localisation"] if severity in {"critical", "high"} else ["Surveiller"],
            "source": _source("model_derived", "Aucun modele client separe n'existe encore; score client derive explicitement du score IA du kit.", "LocalInferenceEngine"),
        })

    return {
        "records": all_records,
        "windows": windows,
        "kits": kits,
        "alerts": alerts,
        "decisions": decisions,
        "interventions": interventions,
        "customers": customers,
        "model_runs": model_runs,
    }


def _not_found(entity: str, entity_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": f"{entity.upper()}_NOT_FOUND",
                "message": f"{entity} introuvable",
                "field": f"{entity}_id",
                "suggestion": "Verifier l'identifiant fourni.",
                "request_id": f"req-{entity_id}",
                "severity": "warning",
                "temporary": False,
            }
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "djua-energy-iot-demo"}


@app.post("/maintenance/predict")
def maintenance_predict(payload: TelemetryWindowRequest) -> dict:
    if not payload.records:
        raise HTTPException(status_code=400, detail="records cannot be empty")
    for record in payload.records:
        validation = validate_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)
    return engine.infer_maintenance(payload.records)


@app.post("/security/predict")
def security_predict(payload: TelemetryWindowRequest) -> dict:
    if not payload.records:
        raise HTTPException(status_code=400, detail="records cannot be empty")
    for record in payload.records:
        validation = validate_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)
    return engine.infer_security(payload.records)


@app.post("/telemetry/analyze")
def telemetry_analyze(payload: TelemetryWindowRequest) -> dict:
    if not payload.records:
        raise HTTPException(status_code=400, detail="records cannot be empty")
    try:
        return telemetry_service.process_window(payload.records)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ai/chat")
def ai_chat(payload: AiChatRequest) -> dict:
    return chat_service.answer(payload.message).to_dict()


@app.get("/telemetry/metrics")
def telemetry_metrics() -> dict:
    return telemetry_service.metrics.snapshot()


@app.get("/telemetry/quarantine")
def telemetry_quarantine() -> dict:
    return {"entries": [entry.__dict__ for entry in telemetry_service.quarantine_store.list_entries()]}


@app.get("/telemetry/audit")
def telemetry_audit() -> dict:
    return {"events": [event.__dict__ for event in telemetry_service.audit_log.list_events()]}


@app.get("/realtime/fleet-state")
def realtime_fleet_state() -> dict:
    states = realtime_store.list_device_states()
    return {
        "device_count": len(states),
        "states": states,
    }


@app.get("/realtime/devices/{device_id}/state")
def realtime_device_state(device_id: str) -> dict:
    state = realtime_store.get_device_state(device_id)
    if state is None:
        raise _not_found("device", device_id)
    return state


@app.get("/realtime/devices/{device_id}/predictions")
def realtime_device_predictions(device_id: str, limit: int = 50) -> dict:
    return {
        "device_id": device_id,
        "history": realtime_store.prediction_history(device_id, limit=limit),
    }


def _live_priority_rank(level: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}.get(str(level).lower(), 0)


def _live_state_summary(state: dict) -> dict:
    latest = state["latest_payload"]
    prediction = state["latest_prediction"]
    return {
        "device_id": state["device_id"],
        "kit_id": state["kit_id"],
        "region": latest.get("region"),
        "status": state["status"],
        "risk_level": state["risk_level"],
        "risk_score": state["risk_score"],
        "alert_priority": state["alert_priority"],
        "recommended_action": state["recommended_action"],
        "last_event_time": state["last_event_time"],
        "last_prediction_at": state["last_prediction_at"],
        "scenario": latest.get("scenario"),
        "battery": {
            "voltage_v": latest.get("battery_voltage_v"),
            "temperature_c": latest.get("battery_temperature_c"),
            "state_of_charge_pct": latest.get("state_of_charge_pct"),
            "state_of_health_pct": latest.get("state_of_health_pct"),
            "age_months": latest.get("battery_age_months"),
        },
        "energy": {
            "solar_power_w": latest.get("solar_power_w"),
            "load_power_w": latest.get("load_power_w"),
            "energy_generated_wh": latest.get("energy_generated_wh"),
            "energy_consumed_wh": latest.get("energy_consumed_wh"),
        },
        "environment": {
            "ambient_temperature_c": latest.get("ambient_temperature_c"),
            "humidity_pct": latest.get("humidity_pct"),
            "season": latest.get("season"),
            "day_period": latest.get("day_period"),
            "solar_irradiance_w_m2": latest.get("solar_irradiance_w_m2"),
        },
        "location": {
            "latitude": latest.get("latitude"),
            "longitude": latest.get("longitude"),
            "gps_accuracy_m": latest.get("gps_accuracy_m"),
            "distance_from_installation_m": latest.get("distance_from_installation_m"),
            "geofence_status": latest.get("geofence_status"),
        },
        "security": {
            "movement_detected": latest.get("movement_detected"),
            "tamper_detected": latest.get("tamper_detected"),
            "enclosure_opened": latest.get("enclosure_opened"),
            "impact_detected": latest.get("impact_detected"),
            "identity_mismatch_detected": latest.get("identity_mismatch_detected"),
        },
        "connectivity": {
            "type": latest.get("connectivity_type"),
            "status": latest.get("connection_status"),
            "network_quality": latest.get("network_quality"),
            "signal_strength_dbm": latest.get("signal_strength_dbm"),
            "connectivity_gap_seconds": latest.get("connectivity_gap_seconds"),
            "operator": latest.get("network_operator"),
        },
        "ai": {
            "prediction_id": prediction.get("prediction_id"),
            "records_used": prediction.get("records_used"),
            "maintenance_probability": prediction.get("maintenance_probability"),
            "security_probability": prediction.get("security_probability"),
            "maintenance_prediction": prediction.get("maintenance_prediction"),
            "security_prediction": prediction.get("security_prediction"),
            "feature_snapshot": prediction.get("feature_snapshot"),
        },
    }


@app.get("/frontend/live/ui")
def frontend_live_ui() -> dict:
    states = realtime_store.list_device_states()
    summaries = [_live_state_summary(state) for state in states]
    sorted_summaries = sorted(
        summaries,
        key=lambda item: (_live_priority_rank(item["risk_level"]), item["risk_score"]),
        reverse=True,
    )
    latest_predictions = [
        item
        for summary in sorted_summaries
        for item in realtime_store.prediction_history(summary["device_id"], limit=5)
    ]
    high_priority = [item for item in sorted_summaries if _live_priority_rank(item["risk_level"]) >= 2]
    total_energy_generated_kwh = round(
        sum(float(item["energy"]["energy_generated_wh"] or 0) for item in summaries) / 1000,
        2,
    )
    offline_count = sum(1 for item in summaries if item["connectivity"]["status"] == "disconnected")
    average_health = round(
        sum(float(item["battery"]["state_of_health_pct"] or 0) for item in summaries) / len(summaries),
        2,
    ) if summaries else 0
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "meta": {
            "schema_version": "frontend-live.v1",
            "generated_at": generated_at,
            "source": "data/runtime/djua_realtime.sqlite",
            "ai_traceability": "Payload construit depuis device_state, prediction_history et telemetry_records.",
        },
        "command_center": {
            "summary": [
                {"id": "devices", "label": "Devices supervises", "value": len(summaries), "unit": "devices"},
                {"id": "priority_alerts", "label": "Alertes a traiter", "value": len(high_priority), "unit": "alerts"},
                {"id": "offline", "label": "Devices hors ligne", "value": offline_count, "unit": "devices"},
                {"id": "battery_health", "label": "Sante batterie moyenne", "value": average_health, "unit": "%"},
                {"id": "energy_generated", "label": "Energie generee", "value": total_energy_generated_kwh, "unit": "kWh"},
            ],
            "priority_alerts": high_priority[:5],
            "recent_activity": latest_predictions[:10],
            "system_status": {"api": "online", "database": "online", "models": "loaded"},
        },
        "decision_detail": {
            "decisions": latest_predictions,
            "open_decision": latest_predictions[0] if latest_predictions else None,
        },
        "digital_twin": {
            "kits": sorted_summaries,
            "default_device_id": sorted_summaries[0]["device_id"] if sorted_summaries else None,
        },
        "fleet_monitoring": {
            "points": [
                {
                    "device_id": item["device_id"],
                    "kit_id": item["kit_id"],
                    "latitude": item["location"]["latitude"],
                    "longitude": item["location"]["longitude"],
                    "risk_level": item["risk_level"],
                    "risk_score": item["risk_score"],
                    "status": item["status"],
                    "connectivity_status": item["connectivity"]["status"],
                    "geofence_status": item["location"]["geofence_status"],
                    "region": item["region"],
                }
                for item in sorted_summaries
            ],
            "filters": ["region", "risk_level", "status", "connectivity_status", "geofence_status"],
        },
        "create_intervention": {
            "recommended_queue": [
                {
                    "device_id": item["device_id"],
                    "kit_id": item["kit_id"],
                    "priority": item["risk_level"],
                    "reason": item["scenario"],
                    "recommended_action": item["recommended_action"],
                }
                for item in high_priority
            ],
            "form_options": {
                "priorities": ["low", "medium", "high", "critical"],
                "statuses": ["draft", "assigned", "in_progress", "completed"],
                "intervention_types": ["battery_check", "security_check", "connectivity_check", "solar_panel_check"],
            },
        },
        "customer_profile": {
            "message": "Les donnees client/paiement ne sont pas encore branchees; rattacher client_id au kit_id dans la prochaine table customers.",
            "kit_risk_context": sorted_summaries,
        },
        "performance": {
            "model_runs": len(latest_predictions),
            "alerts_by_level": {
                level: sum(1 for item in summaries if item["risk_level"] == level)
                for level in ["critical", "high", "medium", "low"]
            },
            "energy_generated_kwh": total_energy_generated_kwh,
            "average_battery_health_pct": average_health,
        },
        "administration": {
            "models": engine.metadata,
            "data_tables": ["telemetry_records", "prediction_history", "device_state"],
            "ingestion_contract": "schemas/telemetry.v1.schema.json",
        },
    }


@app.post("/demo/generate")
def demo_generate() -> dict:
    generator = SyntheticTelemetryGenerator(seed=11, num_kits=2)
    records = generator.generate(scenarios=["normal_operation", "suspicious_movement"], duration_hours=2)
    return {"records": records[:3]}


@app.get("/frontend/command-center")
def frontend_command_center() -> dict:
    demo = _demo_entities()
    kits = demo["kits"]
    alerts = demo["alerts"]
    operational = sum(1 for kit in kits if kit["status"] == "operational")
    at_risk = sum(1 for kit in kits if kit["risk_level"] in {"critical", "high"})
    offline = sum(1 for kit in kits if kit["status"] == "offline")
    by_severity = {
        "critical": sum(1 for decision in demo["decisions"] if decision["severity"] == "critical"),
        "high": sum(1 for decision in demo["decisions"] if decision["severity"] == "high"),
        "medium": sum(1 for decision in demo["decisions"] if decision["severity"] == "medium"),
        "low": sum(1 for decision in demo["decisions"] if decision["severity"] == "low"),
    }
    energy_today = round(sum(float(record.get("energy_generated_wh", 0)) for record in demo["records"]) / 1000, 2)
    return {
        "meta": {
            "schema_version": "frontend.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Les scores, decisions et alertes viennent de LocalInferenceEngine; les KPI energie viennent de la telemetrie; les couts/MTTR restent des hypotheses demo.",
            "model_runs": demo["model_runs"],
        },
        "summary": [
            {**_metric("total_kits", "Kits supervises", len(kits), "count", len(kits), "stable", "neutral"), "source": _source("telemetry_derived", "Comptage des kits dans les fenetres de demo.")},
            {**_metric("operational_kits", "Kits operationnels", operational, "count", max(0, operational - 1), "up", "positive"), "source": _source("telemetry_derived", "Derive du statut de connectivite de la derniere telemetrie.")},
            {**_metric("at_risk_kits", "Kits a risque", at_risk, "count", max(0, at_risk - 1), "up", "negative"), "source": _source("model_derived", "Nombre de kits dont la priorite modele est high ou critical.", "LocalInferenceEngine")},
            {**_metric("offline_kits", "Kits hors ligne", offline, "count", 0, "up", "negative"), "source": _source("telemetry_derived", "Derive de connection_status.")},
            {**_metric("availability_rate", "Disponibilite", round(operational / len(kits) * 100, 1), "percent", 96.5, "down", "negative"), "source": _source("telemetry_derived", "Calcule depuis les statuts de connectivite.")},
            {**_metric("energy_today", "Energie generee aujourd'hui", energy_today, "kWh", round(energy_today * 0.92, 2), "up", "positive"), "source": _source("telemetry_derived", "Somme de energy_generated_wh dans la telemetrie.")},
            {**_metric("co2_avoided", "CO2 evite", round(energy_today * 0.61, 2), "kg", round(energy_today * 0.56, 2), "up", "positive"), "source": _source("telemetry_derived", "Conversion demo a partir de l'energie mesuree; pas une sortie modele.")},
            {**_metric("open_ai_decisions", "Decisions IA ouvertes", sum(1 for decision in demo["decisions"] if decision["status"] == "open"), "count", 2, "up", "neutral"), "source": _source("model_derived", "Decisions ouvertes issues des predictions IA.", "LocalInferenceEngine")},
        ],
        "priority_alerts": alerts,
        "fleet_map": {
            "points": kits,
            "clusters": [{"cluster_id": "cluster-west", "count": len(kits), "risk_level": "high", "latitude": kits[0]["latitude"], "longitude": kits[0]["longitude"]}],
            "heatmaps": [{"type": "risk", "label": "Zones de risque", "points": [{"latitude": kit["latitude"], "longitude": kit["longitude"], "weight": kit["health_score"]} for kit in kits]}],
            "available_filters": ["country", "region", "city", "status", "risk_level", "connectivity_status", "installation_type", "model", "active_intervention_id"],
        },
        "decision_engine": {
            "total": len(demo["decisions"]),
            "by_severity": by_severity,
            "by_status": {
                "open": sum(1 for decision in demo["decisions"] if decision["status"] == "open"),
                "monitoring": sum(1 for decision in demo["decisions"] if decision["status"] == "monitoring"),
            },
            "confirmation_rate": {"value": None, "unit": "percent", "source": _source("not_available", "Pas encore de feedback humain persiste.")},
            "false_positive_rate": {"value": None, "unit": "percent", "source": _source("not_available", "Pas encore de feedback humain persiste.")},
            "average_review_time": {"value": None, "unit": "minutes", "source": _source("not_available", "Pas encore de workflow de revue persiste.")},
            "source": _source("model_derived", "Aggregation des decisions produites par les modeles locaux.", "LocalInferenceEngine"),
        },
        "system_status": [
            {"service": "ingestion", "status": "ok", "message": "Telemetry recue", "availability_percent": 99.9, "last_checked_at": DEMO_NOW, "response_time_ms": 18, "impact": "none"},
            {"service": "ai_service", "status": "ok", "message": "Modeles charges", "availability_percent": 99.5, "last_checked_at": DEMO_NOW, "response_time_ms": 41, "impact": "none"},
            {"service": "iot_connectivity", "status": "degraded", "message": "Un kit hors ligne dans la demo", "availability_percent": 92.0, "last_checked_at": DEMO_NOW, "response_time_ms": 120, "impact": "medium"},
        ],
        "recent_activity": [
            {"event_id": "evt-001", "type": "new_decision", "title": "Decision IA creee", "description": "Suspicion de fraude detectee.", "timestamp": DEMO_NOW, "actor": "djua-risk-engine", "entity": {"type": "decision", "id": "decision-001"}, "severity": "critical", "status": "open"},
            {"event_id": "evt-002", "type": "kit_offline", "title": "Kit hors ligne", "description": "Perte de communication prolongee.", "timestamp": DEMO_NOW, "actor": "iot-ingestion", "entity": {"type": "kit", "id": "kit-0"}, "severity": "high", "status": "open"},
        ],
    }


@app.get("/frontend/decisions/{decision_id}")
def frontend_decision_detail(decision_id: str) -> dict:
    demo = _demo_entities()
    decision = next((item for item in demo["decisions"] if item["decision_id"] == decision_id), None)
    if decision is None:
        raise _not_found("decision", decision_id)
    kit = next(item for item in demo["kits"] if item["kit_id"] == decision["kit_id"])
    records = demo["windows"][decision["kit_id"]]
    risk_factors = _risk_factors(records, decision)
    return {
        "meta": {
            "schema_version": "decision.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "La decision, le score et les sorties brutes viennent du modele. Les facteurs sont les sorties modele et features d'entree; ce ne sont pas encore des valeurs SHAP.",
        },
        "decision": decision,
        "natural_language_explanation": {
            "title": "Ce qui s'est passe",
            "text": (
                f"Le moteur IA a analyse {len(records)} mesures du kit {decision['kit_id']}. "
                f"Le modele maintenance retourne une probabilite de {decision['model_outputs']['maintenance']['technical_risk_probability']} "
                f"et le modele securite retourne un score de {decision['model_outputs']['security']['suspicious_activity_score']}. "
                f"La decision finale est classee {decision['severity']} avec un score consolide de {decision['score']}%. "
                "Les facteurs affiches ci-dessous correspondent aux sorties modele et aux features calculees avant inference."
            ),
        },
        "risk_factors": risk_factors,
        "score_history": {
            "granularity": "30m",
            "thresholds": [{"label": "action", "value": 65}],
            "series": _score_history(records),
            "source": _source("model_output", "Chaque point est recalcule par les modeles sur un prefixe de la fenetre.", "LocalInferenceEngine"),
        },
        "evidence": [
            {"type": "model_output", "source": "maintenance", "value": decision["model_outputs"]["maintenance"], "timestamp": DEMO_NOW, "reliability": "synthetic_model", "relevance": "strong", "explanation": "Sortie brute du modele maintenance local."},
            {"type": "model_output", "source": "security", "value": decision["model_outputs"]["security"], "timestamp": DEMO_NOW, "reliability": "synthetic_model", "relevance": "strong", "explanation": "Sortie brute du modele securite local."},
            {"type": "model_features", "source": "feature_pipeline", "value": decision["feature_snapshot"], "timestamp": records[-1]["event_time"], "reliability": "derived_from_telemetry", "relevance": "strong", "explanation": "Features calculees avant inference et utilisees pour expliquer la decision."},
            {"type": "telemetry", "source": "iot_synthetic", "value": records[-1], "timestamp": records[-1]["event_time"], "reliability": "synthetic_demo", "relevance": "medium", "explanation": "Derniere mesure brute de la fenetre analysee."},
        ],
        "timeline": [
            {"timestamp": records[0]["event_time"], "type": "telemetry_received", "title": "Debut de fenetre telemetrie", "status": "done", "source": _source("telemetry", "Premier record utilise par le modele.")},
            {"timestamp": records[-1]["event_time"], "type": "features_computed", "title": "Features calculees", "status": "done", "source": _source("model_feature", "build_maintenance_features et build_security_features.")},
            {"timestamp": DEMO_NOW, "type": "model_inference", "title": "Inference maintenance et securite executee", "status": "done", "source": _source("model_output", "engine.infer_maintenance et engine.infer_security.", "LocalInferenceEngine")},
            {"timestamp": DEMO_NOW, "type": "decision_generated", "title": "Decision IA generee", "status": decision["status"], "source": decision["source"]},
        ],
        "recommendations": [next(item for item in demo["interventions"] if item["decision_id"] == decision_id)],
        "feedback_options": ["confirmed", "rejected", "false_positive", "fraud_confirmed", "failure_confirmed", "no_anomaly"],
    }


@app.get("/frontend/interventions/create")
def frontend_create_intervention(decision_id: str = "decision-001") -> dict:
    demo = _demo_entities()
    decision = next((item for item in demo["decisions"] if item["decision_id"] == decision_id), None)
    if decision is None:
        raise _not_found("decision", decision_id)
    kit = next(item for item in demo["kits"] if item["kit_id"] == decision["kit_id"])
    customer = next(item for item in demo["customers"] if item["client_id"] == decision["client_id"])
    recommendation = next(item for item in demo["interventions"] if item["decision_id"] == decision_id)
    related_alert = next((item for item in demo["alerts"] if item["decision_id"] == decision_id), None)
    priority = recommendation["priority"]
    default_due_at = "2026-07-20T16:00:00Z" if priority == "critical" else "2026-07-22T16:00:00Z"
    default_technician_id = "tech-001" if recommendation["recommended_type"] == "fraud_check" else "tech-002"
    return {
        "meta": {
            "schema_version": "create-intervention.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Le kit, la priorite, le motif et la justification viennent de la decision IA; techniciens, couts et planning sont des donnees demo non connectees a un outil terrain Orange.",
        },
        "context": {
            "decision": decision,
            "alert": related_alert,
            "kit": kit,
            "customer": customer,
            "source": _source("model_derived", "Contexte pre-rempli depuis la decision IA et le kit rattache.", "LocalInferenceEngine"),
        },
        "draft": {
            "intervention_id": recommendation["intervention_id"],
            "decision_id": decision_id,
            "kit_id": kit["kit_id"],
            "client_id": customer["client_id"],
            "type": recommendation["recommended_type"],
            "priority": priority,
            "urgency": recommendation["urgency"],
            "status": "draft",
            "reason": decision["summary"],
            "justification": recommendation["justification"],
            "assigned_team": "field-security" if recommendation["recommended_type"] == "fraud_check" else "field-maintenance",
            "assigned_technician_id": default_technician_id,
            "scheduled_start_at": None,
            "due_at": default_due_at,
            "estimated_duration_minutes": recommendation["estimated_duration_minutes"],
            "estimated_cost": recommendation["estimated_cost"],
            "required_skills": recommendation["required_skills"],
            "checklist": recommendation["checklist"],
            "source": recommendation["source"],
        },
        "form_options": {
            "types": [
                {"value": "fraud_check", "label": "Controle fraude / deplacement", "default_for": ["security"]},
                {"value": "preventive_maintenance", "label": "Maintenance preventive", "default_for": ["maintenance"]},
                {"value": "battery_replacement", "label": "Remplacement batterie", "default_for": ["maintenance"]},
                {"value": "connectivity_diagnostic", "label": "Diagnostic connectivite", "default_for": ["connectivity", "security"]},
            ],
            "priorities": ["critical", "high", "medium", "low"],
            "urgencies": ["same_day", "next_day", "this_week", "monitoring"],
            "teams": [
                {"team_id": "field-security", "label": "Equipe controle terrain", "skills": ["diagnostic_iot", "controle_gps"]},
                {"team_id": "field-maintenance", "label": "Equipe maintenance solaire", "skills": ["maintenance_batterie", "diagnostic_iot"]},
            ],
            "technicians": [
                {"technician_id": "tech-001", "name": "Technicien demo A", "team_id": "field-security", "region": kit["region"], "skills": ["diagnostic_iot", "controle_gps"], "availability": "available", "source": _source("demo_static", "Technicien fictif pour la demonstration.")},
                {"technician_id": "tech-002", "name": "Technicien demo B", "team_id": "field-maintenance", "region": kit["region"], "skills": ["maintenance_batterie", "diagnostic_iot"], "availability": "available", "source": _source("demo_static", "Technicien fictif pour la demonstration.")},
            ],
            "time_slots": [
                {"slot_id": "slot-001", "start_at": "2026-07-20T13:00:00Z", "end_at": "2026-07-20T15:00:00Z", "capacity": 1, "source": _source("demo_static", "Planning terrain non connecte.")},
                {"slot_id": "slot-002", "start_at": "2026-07-21T09:00:00Z", "end_at": "2026-07-21T11:00:00Z", "capacity": 2, "source": _source("demo_static", "Planning terrain non connecte.")},
            ],
        },
        "validation_rules": [
            {"field": "kit_id", "rule": "required"},
            {"field": "type", "rule": "required"},
            {"field": "priority", "rule": "required"},
            {"field": "assigned_technician_id", "rule": "required_before_confirm"},
            {"field": "scheduled_start_at", "rule": "required_before_confirm"},
        ],
        "actions": [
            {"id": "save_draft", "label": "Sauvegarder brouillon", "enabled": True, "method": "POST", "endpoint": None, "source": _source("not_available", "Pas encore de persistance intervention.")},
            {"id": "confirm_intervention", "label": "Confirmer intervention", "enabled": False, "method": "POST", "endpoint": None, "disabled_reason": "Creation persistante non implementee dans le MVP actuel.", "source": _source("not_available", "Workflow d'ecriture a ajouter cote backend.")},
        ],
    }


@app.get("/frontend/kits/{kit_id}/digital-twin")
def frontend_kit_digital_twin(kit_id: str) -> dict:
    demo = _demo_entities()
    kit = next((item for item in demo["kits"] if item["kit_id"] == kit_id), None)
    if kit is None:
        raise _not_found("kit", kit_id)
    records = demo["windows"][kit_id]
    latest = records[-1]
    return {
        "meta": {
            "schema_version": "kit-digital-twin.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Sante et maintenance_prediction derivent des sorties modele; mesures batterie/solaire/connectivite viennent de la derniere telemetrie.",
        },
        "identity": {**kit, "firmware": {"version": "1.0.0", "status": "up_to_date"}, "uptime": {"value": 99.1, "unit": "percent"}},
        "health": {"score": kit["health_score"], "level": kit["risk_level"], "trend": "down" if kit["risk_level"] != "low" else "stable", "confidence": 0.81, "prediction_horizon": "7d", "recommendation": kit["model_outputs"]["maintenance"]["recommended_action"], "source": _source("model_derived", "Score sante = 100 - score de risque modele consolide.", "LocalInferenceEngine")},
        "battery": {"voltage": {"value": latest["battery_voltage_v"], "unit": "V"}, "temperature": {"value": latest["battery_temperature_c"], "unit": "celsius"}, "soc": {"value": latest["state_of_charge_pct"], "unit": "percent"}, "soh": {"value": latest["state_of_health_pct"], "unit": "percent"}, "status": "watch" if kit["risk_level"] != "low" else "ok", "source": _source("telemetry", "Derniere telemetrie du kit.")},
        "solar": {"power": {"value": latest["solar_power_w"], "unit": "W"}, "energy_today": {"value": round(float(latest["energy_generated_wh"]) / 1000, 3), "unit": "kWh"}, "yield": {"value": round(float(latest["solar_power_w"]) / max(float(latest["solar_irradiance_w_m2"]), 1) * 100, 2), "unit": "percent"}, "status": "ok", "source": _source("telemetry_derived", "Mesures et ratio calcules depuis la telemetrie.")},
        "load": {"power": {"value": latest["load_power_w"], "unit": "W"}, "profile": latest["usage_profile"], "abnormal_consumption": latest["abnormal_consumption_detected"], "status": "watch" if latest["abnormal_consumption_detected"] else "ok", "source": _source("telemetry", "Derniere telemetrie du kit.")},
        "connectivity": {"network": latest["connectivity_type"], "status": kit["connectivity_status"], "signal_strength_dbm": latest["signal_strength_dbm"], "last_communication_at": latest["last_successful_sync_at"], "packet_loss_ratio": latest["packet_loss_ratio"], "source": _source("telemetry", "Derniere telemetrie du kit.")},
        "physical_security": {"movement_detected": latest["movement_detected"], "enclosure_opened": latest["enclosure_opened"], "geofence_status": latest["geofence_status"], "risk_level": kit["risk_level"], "source": _source("model_derived", "Risque securite derive du modele, signaux bruts depuis telemetrie.", "security")},
        "location": {"latitude": kit["latitude"], "longitude": kit["longitude"], "accuracy_m": kit["gps_accuracy_m"], "city": kit["city"], "region": kit["region"], "country": kit["country"], "geofence_status": latest["geofence_status"], "source": _source("telemetry", "Position GPS de la derniere telemetrie.")},
        "components": [
            {"name": "battery", "type": "storage", "status": "watch" if kit["model_outputs"]["maintenance"]["risk_level"] == "high" else "ok", "health_score": kit["health_score"], "current_value": latest["battery_voltage_v"], "unit": "V", "risk": kit["model_outputs"]["maintenance"]["risk_level"], "recommendation": kit["model_outputs"]["maintenance"]["recommended_action"], "source": _source("model_derived", "Risque batterie derive du modele maintenance.", "maintenance")},
            {"name": "iot_module", "type": "connectivity", "status": kit["connectivity_status"], "health_score": max(0, 100 - round(float(kit["model_outputs"]["security"]["suspicious_activity_score"]) * 100)), "current_value": latest["signal_strength_dbm"], "unit": "dBm", "risk": kit["model_outputs"]["security"]["risk_level"], "recommendation": kit["model_outputs"]["security"]["recommended_action"], "source": _source("model_derived", "Risque module IoT derive du modele securite.", "security")},
        ],
        "telemetry": {"granularity": "30m", "series": [{"timestamp": record["event_time"], "battery_voltage_v": record["battery_voltage_v"], "solar_power_w": record["solar_power_w"], "battery_temperature_c": record["battery_temperature_c"], "state_of_charge_pct": record["state_of_charge_pct"]} for record in records], "source": _source("telemetry", "Fenetre exacte envoyee aux modeles.")},
        "events": [{"event_id": "evt-kit-001", "type": "score_changed", "timestamp": DEMO_NOW, "severity": kit["risk_level"], "description": "Score de sante actualise depuis les sorties modele.", "source": _source("model_derived", "Evenement derive du score modele.", "LocalInferenceEngine")}],
        "maintenance_prediction": {"failure_probability": kit["model_outputs"]["maintenance"]["technical_risk_probability"], "horizon": "7d", "component": kit["model_outputs"]["maintenance"]["suspected_component"], "confidence": 0.79, "priority": kit["risk_level"], "suggested_action": kit["model_outputs"]["maintenance"]["recommended_action"], "raw_model_output": kit["model_outputs"]["maintenance"], "source": _source("model_output", "Sortie directe infer_maintenance.", "maintenance")},
    }


@app.get("/frontend/fleet")
def frontend_fleet() -> dict:
    demo = _demo_entities()
    kits = demo["kits"]
    return {
        "meta": {
            "schema_version": "fleet.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "La colonne risk_level et model_score vient des predictions. Les positions et statuts connectivite viennent de la telemetrie.",
            "model_runs": demo["model_runs"],
        },
        "summary": {
            "total_kits": len(kits),
            "online": sum(1 for kit in kits if kit["status"] == "operational"),
            "offline": sum(1 for kit in kits if kit["status"] == "offline"),
            "at_risk": sum(1 for kit in kits if kit["risk_level"] != "low"),
            "in_intervention": sum(1 for kit in kits if kit["active_intervention_id"]),
            "anomalies": len(demo["alerts"]),
            "source": _source("mixed", "Statuts depuis telemetrie; risque et anomalies depuis sorties modele.", "LocalInferenceEngine"),
        },
        "kits": kits,
        "pagination": {"page": 1, "page_size": len(kits), "total": len(kits), "total_pages": 1, "next_page": None, "previous_page": None, "sort": "risk_level:desc", "filters": {}},
        "map": {"points": kits, "layers": ["clusters", "heatmap", "risk_zones", "offline_zones"]},
        "location_history": [
            {
                "kit_id": kit_id,
                "points": [
                    {
                        "timestamp": record["event_time"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "speed_mps": record["speed_mps"],
                        "geofence_status": record["geofence_status"],
                    }
                    for record in records
                ],
                "source": _source("telemetry", "Historique GPS issu de la fenetre envoyee au modele."),
            }
            for kit_id, records in demo["windows"].items()
        ],
    }


@app.get("/frontend/customers/{client_id}/risk-profile")
def frontend_customer_risk_profile(client_id: str) -> dict:
    demo = _demo_entities()
    customer = next((item for item in demo["customers"] if item["client_id"] == client_id), None)
    if customer is None:
        raise _not_found("client", client_id)
    kit = next(item for item in demo["kits"] if item["client_id"] == client_id)
    records = demo["windows"][kit["kit_id"]]
    latest = records[-1]
    return {
        "meta": {
            "schema_version": "customer-risk.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Il n'existe pas encore de modele client dedie; le risque client est explicitement derive des modeles kit maintenance/securite.",
        },
        "customer": customer,
        "payment_risk": {"score": None, "level": "not_available", "late_payments": None, "amount_due": None, "trend": "not_available", "source": _source("not_available", "Aucun modele paiement ni donnees paiement branchees dans ce MVP.")},
        "consumption": {"average_wh": round(sum(float(record["energy_consumed_wh"]) for record in records) / len(records), 2), "trend": "stable", "anomaly": latest["abnormal_consumption_detected"], "comparison": "calcule uniquement sur la fenetre du kit", "source": _source("telemetry_derived", "Moyenne energy_consumed_wh sur les records du kit.")},
        "kit_risk": {"kit_moved": latest["movement_detected"], "kit_opened": latest["enclosure_opened"], "offline": latest["connection_status"] == "disconnected", "model_score": kit["model_score"], "maintenance_prediction": kit["model_outputs"]["maintenance"], "security_prediction": kit["model_outputs"]["security"], "source": _source("model_output", "Risque client rattache aux predictions du kit.", "LocalInferenceEngine")},
        "recommendations": [{"label": item, "justification": "Action proposee selon le score client et les signaux kit."} for item in customer["recommendations"]],
    }


@app.get("/frontend/performance")
def frontend_performance() -> dict:
    demo = _demo_entities()
    energy_generated = round(sum(float(record.get("energy_generated_wh", 0)) for record in demo["records"]) / 1000, 2)
    open_decisions = sum(1 for decision in demo["decisions"] if decision["status"] == "open")
    model_metadata = engine.metadata
    return {
        "meta": {
            "schema_version": "performance.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Les performances modeles viennent de artifacts/metadata.json. Les KPI operationnels disponibles sont derives des predictions et de la telemetrie.",
        },
        "operational_kpis": [
            {**_metric("open_ai_decisions", "Decisions IA ouvertes", open_decisions, "count", 0, "up", "negative", "demo_window"), "source": _source("model_derived", "Compte des decisions ouvertes produites par les modeles.", "LocalInferenceEngine")},
            {**_metric("critical_decisions", "Decisions critiques", sum(1 for decision in demo["decisions"] if decision["severity"] == "critical"), "count", 0, "up", "negative", "demo_window"), "source": _source("model_derived", "Compte des severites issues de la priorisation modele.", "LocalInferenceEngine")},
            {"id": "mttr", "label": "MTTR", "value": None, "unit": "hours", "state": "unknown", "source": _source("not_available", "Pas encore de resultats d'intervention persistants.")},
            {"id": "confirmation_rate", "label": "Taux de confirmation", "value": None, "unit": "percent", "state": "unknown", "source": _source("not_available", "Pas encore de feedback humain persiste.")},
        ],
        "energy_impact": {"generated": {"value": energy_generated, "unit": "kWh"}, "saved": {"value": None, "unit": "kWh"}, "co2_avoided": {"value": round(energy_generated * 0.61, 2), "unit": "kg"}, "method": "Energie generee depuis telemetrie synthetique; CO2 derive par facteur demo; energie sauvee non disponible sans baseline reelle.", "source": _source("telemetry_derived", "Somme energy_generated_wh.")},
        "financial_impact": {"estimated_savings": None, "avoided_losses": None, "roi": None, "methodology": "Non calcule par les modeles actuels. Il faut une table couts/interventions/fraudes confirmees.", "uncertainty": "not_available", "source": _source("not_available", "Aucun modele financier ni donnees couts branchees.")},
        "models": [
            {"name": "maintenance", "version": model_metadata["maintenance"]["model_version"], "accuracy": model_metadata["maintenance"]["accuracy"], "precision": None, "recall": None, "f1": None, "false_positive_rate": None, "training_rows": model_metadata["maintenance"]["training_rows"], "evaluation_period": "synthetic_training_metadata", "health": "demo_only", "features": model_metadata["maintenance"]["features"], "limitations": model_metadata["maintenance"]["limitations"], "source": _source("artifact_metadata", "Metadonnees chargees depuis artifacts/metadata.json.", "maintenance")},
            {"name": "security", "version": model_metadata["security"]["model_version"], "accuracy": model_metadata["security"]["accuracy"], "precision": None, "recall": None, "f1": None, "false_positive_rate": None, "training_rows": model_metadata["security"]["training_rows"], "evaluation_period": "synthetic_training_metadata", "health": "demo_only", "features": model_metadata["security"]["features"], "limitations": model_metadata["security"]["limitations"], "source": _source("artifact_metadata", "Metadonnees chargees depuis artifacts/metadata.json.", "security")},
        ],
        "drift": {"data_drift": "not_available", "feature_drift": "not_available", "prediction_drift": "not_available", "threshold": None, "recommendation": "Ajouter un monitoring MLOps sur donnees reelles avant d'afficher une derive.", "source": _source("not_available", "Les modeles actuels ne calculent pas la derive.")},
    }


@app.get("/frontend/admin/data-ai")
def frontend_admin_data_ai() -> dict:
    model_metadata = engine.metadata
    return {
        "meta": {"schema_version": "admin-data-ai.v1", "generated_at": DEMO_NOW, "data_mode": "synthetic_demo", "ai_traceability": "Etat technique lu depuis le moteur charge et ses metadonnees locales."},
        "models": [
            {"name": "maintenance", "version": model_metadata["maintenance"]["model_version"], "status": "loaded", "environment": "local", "trained_at": None, "schema_version": "telemetry.v1", "accuracy": model_metadata["maintenance"]["accuracy"], "features": model_metadata["maintenance"]["features"], "source": _source("artifact_metadata", "Modele joblib charge par LocalInferenceEngine.", "maintenance")},
            {"name": "security", "version": model_metadata["security"]["model_version"], "status": "loaded", "environment": "local", "trained_at": None, "schema_version": "telemetry.v1", "accuracy": model_metadata["security"]["accuracy"], "features": model_metadata["security"]["features"], "source": _source("artifact_metadata", "Modele joblib charge par LocalInferenceEngine.", "security")},
        ],
        "pipelines": [{"name": "ingestion", "status": "ok", "last_run_at": DEMO_NOW, "metrics": telemetry_service.metrics.snapshot(), "source": _source("runtime_metrics", "Metriques en memoire de TelemetryIngestionService.")}, {"name": "feature_pipeline", "status": "ok", "last_run_at": DEMO_NOW, "maintenance_features": model_metadata["maintenance"]["features"], "security_features": model_metadata["security"]["features"], "source": _source("artifact_metadata", "Features attendues par les modeles.")}],
        "data_quality": {"completeness_pct": None, "late_data": None, "validation_errors": None, "message": "Qualite globale non calculee ici; consulter /telemetry/quarantine pour les rejets runtime.", "source": _source("not_available", "Pas encore de job data quality global branche a cette route.")},
    }


@app.get("/frontend/realtime/events")
def frontend_realtime_events() -> dict:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    demo = _demo_entities()
    first_decision = demo["decisions"][0]
    first_kit = demo["kits"][0]
    return {
        "meta": {"schema_version": "realtime-events.v1", "generated_at": now, "transport": "polling_demo", "upgrade_path": "SSE ou WebSocket", "ai_traceability": "Evenements generes depuis les decisions modele courantes; transport temps reel non encore persistant."},
        "subscriptions": ["global", "region", "kit", "decision", "event_type", "severity"],
        "events": [
            {"event_id": "rt-001", "type": "new_telemetry", "version": 1, "timestamp": now, "entity": {"type": "kit", "id": first_kit["kit_id"]}, "old_values": {}, "new_values": {"connection_status": first_kit["connectivity_status"], "model_score": first_kit["model_score"]}, "severity": first_kit["risk_level"], "source": _source("model_derived", "Evenement derive de la derniere fenetre analysee.", "LocalInferenceEngine"), "correlation_id": "corr-demo-001", "message": "Nouvelle telemetrie analysee par le modele.", "suggested_action": "Actualiser la carte et les alertes."},
            {"event_id": "rt-002", "type": "score_changed", "version": 1, "timestamp": now, "entity": {"type": "decision", "id": first_decision["decision_id"]}, "old_values": {}, "new_values": {"score": first_decision["score"], "maintenance_probability": first_decision["model_outputs"]["maintenance"]["technical_risk_probability"], "security_probability": first_decision["model_outputs"]["security"]["suspicious_activity_score"]}, "severity": first_decision["severity"], "source": _source("model_output", "Score calcule par infer_maintenance et infer_security.", "LocalInferenceEngine"), "correlation_id": "corr-demo-002", "message": "Score IA actualise.", "suggested_action": "Ouvrir la decision."},
        ],
    }
