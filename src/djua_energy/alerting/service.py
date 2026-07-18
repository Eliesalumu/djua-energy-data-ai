"""Build alert payloads from model predictions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
) -> AlertDecision:
    maintenance_priority = prioritize_maintenance(maintenance_prediction)
    security_priority = prioritize_security(security_prediction)
    priority = prioritize_predictions(maintenance_prediction, security_prediction)
    return AlertDecision(
        device_id=device_id,
        priority=priority,
        maintenance_priority=maintenance_priority,
        security_priority=security_priority,
        maintenance_prediction=maintenance_prediction,
        security_prediction=security_prediction,
        recommended_action=recommended_action(priority),
    )
