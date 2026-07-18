"""Alert priority rules for maintenance and security predictions."""

from __future__ import annotations

from typing import Any


PRIORITY_RANK = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def highest_priority(*priorities: str) -> str:
    return max(priorities, key=lambda item: PRIORITY_RANK.get(item, 0))


def prioritize_maintenance(prediction: dict[str, Any]) -> str:
    probability = float(prediction.get("technical_risk_probability", 0.0))
    if prediction.get("risk_level") != "high":
        return "none"
    if probability >= 0.8:
        return "high"
    return "medium"


def prioritize_security(prediction: dict[str, Any]) -> str:
    probability = float(prediction.get("suspicious_activity_score", 0.0))
    if prediction.get("risk_level") != "high":
        return "none"
    if probability >= 0.8:
        return "critical"
    return "high"


def prioritize_predictions(
    maintenance_prediction: dict[str, Any],
    security_prediction: dict[str, Any],
) -> str:
    return highest_priority(
        prioritize_maintenance(maintenance_prediction),
        prioritize_security(security_prediction),
    )
