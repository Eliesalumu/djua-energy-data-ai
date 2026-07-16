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
        prediction = self.maintenance_model.predict(df[self.maintenance_features])[0]
        return {
            "technical_risk_probability": round(float(probabilities[0]), 3),
            "risk_level": "high" if prediction == 1 else "normal",
            "suspected_component": "battery" if prediction == 1 else "none",
            "top_factors": ["battery_voltage_trend", "battery_temp_trend"],
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
            probability = float(probabilities[0]) if len(probabilities) else 0.0
            prediction = int(self.security_model.predict(df[self.security_features])[0])
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
