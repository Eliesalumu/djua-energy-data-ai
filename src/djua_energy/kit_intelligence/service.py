from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from djua_energy.pipeline.inference import LocalInferenceEngine


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _level(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _risk_probability_to_score(value: float) -> int:
    return max(0, min(100, round(value * 100 if value <= 1 else value)))


def _reason_codes(
    latest: dict[str, Any],
    maintenance_prediction: dict[str, Any],
    security_prediction: dict[str, Any],
    operational_score: int,
) -> list[str]:
    codes: list[str] = []
    if float(maintenance_prediction.get("technical_risk_probability", 0)) >= 0.7:
        codes.append("HIGH_TECHNICAL_RISK")
    if float(security_prediction.get("suspicious_activity_score", 0)) >= 0.7:
        codes.append("HIGH_SECURITY_RISK")
    if float(latest.get("state_of_health_pct", 100) or 100) < 80:
        codes.append("LOW_STATE_OF_HEALTH")
    if latest.get("geofence_status") == "outside":
        codes.append("GEOFENCE_EXIT")
    if latest.get("movement_detected"):
        codes.append("SUSPICIOUS_MOVEMENT")
    if latest.get("connection_status") == "disconnected":
        codes.append("CONNECTIVITY_LOSS")
    if operational_score >= 70:
        codes.append("HIGH_OPERATIONAL_RISK")
    return codes or ["NO_MAJOR_RISK_SIGNAL"]


def build_kit_intelligence(
    *,
    records: list[dict[str, Any]],
    inference_engine: LocalInferenceEngine,
    prediction_id: str | None = None,
    maintenance_prediction: dict[str, Any] | None = None,
    security_prediction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Synthese frontend/scoring: transforme deux predictions modele en un etat operationnel du kit.
    if not records:
        raise ValueError("records cannot be empty")

    latest = records[-1]
    maintenance_prediction = maintenance_prediction or inference_engine.infer_maintenance(records)
    security_prediction = security_prediction or inference_engine.infer_security(records)
    maintenance_score = _risk_probability_to_score(float(maintenance_prediction["technical_risk_probability"]))
    security_score = _risk_probability_to_score(float(security_prediction["suspicious_activity_score"]))
    # Pour l'intervention, le risque operationnel suit le pire signal technique observe.
    operational_score = max(maintenance_score, security_score)
    reason_codes = _reason_codes(latest, maintenance_prediction, security_prediction, operational_score)

    return {
        "kit_id": latest.get("kit_id"),
        "device_id": latest.get("device_id"),
        "evaluated_at": _now_iso(),
        "event_time": latest.get("event_time"),
        "maintenance": {
            "risk_probability": maintenance_prediction["technical_risk_probability"],
            "risk_level": maintenance_prediction["risk_level"],
            "suspected_component": maintenance_prediction.get("suspected_component"),
            "recommended_action": maintenance_prediction.get("recommended_action"),
            "raw_prediction": maintenance_prediction,
        },
        "security": {
            "risk_probability": security_prediction["suspicious_activity_score"],
            "risk_level": security_prediction["risk_level"],
            "suspected_event_types": security_prediction.get("suspected_event_types", []),
            "recommended_action": security_prediction.get("recommended_action"),
            "raw_prediction": security_prediction,
        },
        "operational_risk": {
            "score": operational_score,
            "level": _level(operational_score),
        },
        "reason_codes": reason_codes,
        "data_quality": {
            "status": "good",
            "records_used": len(records),
            "missing_features": [],
            "warnings": [],
        },
        "model_versions": {
            "maintenance": maintenance_prediction.get("model_version"),
            "security": security_prediction.get("model_version"),
        },
        "source_prediction_ids": [prediction_id] if prediction_id else [],
        "legacy_flat": {
            "maintenance_risk": maintenance_prediction["technical_risk_probability"],
            "security_risk": security_prediction["suspicious_activity_score"],
            "battery_health": "degraded" if float(latest.get("state_of_health_pct", 100) or 100) < 80 else "healthy",
            "critical_anomaly": operational_score >= 85,
        },
    }
