"""Build alert payloads from model predictions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from djua_energy.alerting.prioritization import (
    prioritize_maintenance,
    prioritize_predictions,
    prioritize_security,
)


@dataclass(frozen=True)
class AlertDecision:
    device_id: str
    priority: str
    maintenance_priority: str
    security_priority: str
    maintenance_prediction: dict[str, Any]
    security_prediction: dict[str, Any]
    recommended_action: str
    alert_id: str = ""
    kit_id: str | None = None
    event_time: str | None = None
    created_at: str = ""
    maintenance_risk: float = 0.0
    security_risk: float = 0.0
    operational_risk: int = 0
    priority_score: int = 0
    priority_level: str = "none"
    reason_codes: list[str] | None = None
    suspected_components: list[str] | None = None
    suspected_events: list[str] | None = None
    human_review_required: bool = False
    model_versions: dict[str, Any] | None = None
    data_quality: dict[str, Any] | None = None
    source_prediction_ids: list[str] | None = None
    status: str = "open"


def recommended_action(priority: str) -> str:
    if priority == "critical":
        return "Dispatch field team immediately."
    if priority == "high":
        return "Create urgent intervention ticket."
    if priority == "medium":
        return "Schedule technical inspection."
    if priority == "low":
        return "Monitor device."
    return "No alert required."


def build_alert_decision(
    device_id: str,
    maintenance_prediction: dict[str, Any],
    security_prediction: dict[str, Any],
    kit_id: str | None = None,
    event_time: str | None = None,
    data_quality: dict[str, Any] | None = None,
    source_prediction_ids: list[str] | None = None,
) -> AlertDecision:
    maintenance_priority = prioritize_maintenance(maintenance_prediction)
    security_priority = prioritize_security(security_prediction)
    priority = prioritize_predictions(maintenance_prediction, security_prediction)
    maintenance_risk = float(maintenance_prediction.get("technical_risk_probability", 0.0))
    security_risk = float(security_prediction.get("suspicious_activity_score", 0.0))
    priority_score = round(max(maintenance_risk, security_risk) * 100)
    reason_codes = []
    if maintenance_risk >= 0.7:
        reason_codes.append("HIGH_TECHNICAL_RISK")
    if security_risk >= 0.7:
        reason_codes.append("HIGH_SECURITY_RISK")
    if priority == "none":
        reason_codes.append("NO_ALERT_REQUIRED")
    return AlertDecision(
        device_id=device_id,
        priority=priority,
        maintenance_priority=maintenance_priority,
        security_priority=security_priority,
        maintenance_prediction=maintenance_prediction,
        security_prediction=security_prediction,
        recommended_action=recommended_action(priority),
        alert_id=f"alert-{uuid4().hex[:12]}",
        kit_id=kit_id,
        event_time=event_time,
        created_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        maintenance_risk=maintenance_risk,
        security_risk=security_risk,
        operational_risk=priority_score,
        priority_score=priority_score,
        priority_level=priority,
        reason_codes=reason_codes,
        suspected_components=[maintenance_prediction.get("suspected_component")]
        if maintenance_prediction.get("suspected_component") not in {None, "none"}
        else [],
        suspected_events=security_prediction.get("suspected_event_types", []),
        human_review_required=priority in {"high", "critical"},
        model_versions={
            "maintenance": maintenance_prediction.get("model_version"),
            "security": security_prediction.get("model_version"),
        },
        data_quality=data_quality or {"status": "partial", "warnings": ["DATA_QUALITY_NOT_ASSESSED"]},
        source_prediction_ids=source_prediction_ids or [],
        status="open" if priority != "none" else "dismissed",
    )
