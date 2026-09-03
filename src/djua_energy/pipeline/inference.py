from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from djua_energy.pipeline.features import build_maintenance_features, build_security_features


class LocalInferenceEngine:
    def __init__(self, artifact_dir: str | Path | None = None):
        self.artifact_dir = Path(artifact_dir or "artifacts")
        self.maintenance_model = joblib.load(self.artifact_dir / "maintenance_model.joblib")
        self.security_model = joblib.load(self.artifact_dir / "security_model.joblib")
        self.maintenance_features = joblib.load(self.artifact_dir / "maintenance_features.joblib")
        self.security_features = joblib.load(self.artifact_dir / "security_features.joblib")
        self.metadata = json.loads((self.artifact_dir / "metadata.json").read_text(encoding="utf-8"))

    def infer_maintenance(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        df = build_maintenance_features(records)
        probabilities = self.maintenance_model.predict_proba(df[self.maintenance_features])[:, 1]
        predictions = self.maintenance_model.predict(df[self.maintenance_features])
        latest_index = -1
        latest = records[-1]
        model_probability = float(probabilities[latest_index])
        rule_probability = 0.0
        if float(latest.get("battery_voltage_v", 99) or 99) <= 12.1:
            rule_probability = max(rule_probability, 0.85)
        if float(latest.get("state_of_health_pct", 100) or 100) <= 75:
            rule_probability = max(rule_probability, 0.85)
        if latest.get("overload_detected") or latest.get("abnormal_consumption_detected"):
            rule_probability = max(rule_probability, 0.7)
        probability = max(model_probability, rule_probability)
        prediction = 1 if probability >= 0.65 else int(predictions[latest_index])
        return {
            "technical_risk_probability": round(probability, 3),
            "risk_level": "high" if prediction == 1 else "normal",
            "suspected_component": "battery" if prediction == 1 else "none",
            "top_factors": ["battery_voltage_trend", "battery_voltage_volatility"],
            "rule_warnings": ["synthetic-data-only"],
            "recommended_action": "inspect device", 
            "model_version": self.metadata["maintenance"]["model_version"],
            "trained_on_synthetic_data": True,
            "human_review_required": True,
            "limitations": self.metadata["maintenance"]["limitations"],
        }

    def infer_security(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        df = build_security_features(records)
        if len(self.security_model.classes_) < 2:
            probability = 0.25
            prediction = 0
        else:
            probabilities = self.security_model.predict_proba(df[self.security_features])[:, 1]
            predictions = self.security_model.predict(df[self.security_features])
            probability = float(probabilities[-1]) if len(probabilities) else 0.0
            prediction = int(predictions[-1]) if len(predictions) else 0
        latest = records[-1]
        if latest.get("geofence_status") == "outside" or latest.get("enclosure_opened"):
            probability = max(probability, 0.9)
            prediction = 1
        return {
            "suspicious_activity_score": round(probability, 3),
            "risk_level": "high" if prediction == 1 else "normal",
            "suspected_event_types": ["suspicious_movement"] if prediction == 1 else [],
            "evidence": ["synthetic telemetry window"],
            "rule_warnings": ["human_review_required"],
            "recommended_action": "verify physical state",
            "model_version": self.metadata["security"]["model_version"],
            "trained_on_synthetic_data": True,
            "human_review_required": True,
            "fraud_confirmed": False,
        }
