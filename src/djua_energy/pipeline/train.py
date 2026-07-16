from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupShuffleSplit

from djua_energy.pipeline.features import build_maintenance_features, build_security_features
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.contracts import validate_payload


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def train_models(output_dir: str | Path | None = None) -> dict[str, Any]:
    output_dir = Path(output_dir or ARTIFACT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    generator = SyntheticTelemetryGenerator(seed=7, num_kits=4)
    records = generator.generate(scenarios=[
        "normal_operation",
        "progressive_battery_degradation",
        "battery_overheating",
        "rapid_discharge",
        "unstable_voltage",
        "low_solar_input",
        "suspicious_movement",
        "tamper_attempt",
        "movement_then_connectivity_loss",
        "geofence_exit",
    ], duration_hours=8)

    for payload in records:
        validation = validate_payload(payload)
        if not validation["valid"]:
            raise ValueError(f"Invalid payload: {validation['errors']}")

    maintenance_df = build_maintenance_features(records)
    maintenance_df["target_technical_anomaly"] = (
        (maintenance_df["battery_voltage_trend"] < -0.05)
        | (maintenance_df["battery_temp_trend"] > 5)
        | (maintenance_df["solar_controller_instability"] == 1)
        | (maintenance_df["overload_signal"] == 1)
        | (maintenance_df["short_circuit_signal"] == 1)
    ).astype(int)
    maintenance_df["target_battery_degradation"] = (maintenance_df["soc_drop"] < -2).astype(int)
    maintenance_df["target_overheating"] = (maintenance_df["battery_temp_trend"] > 3).astype(int)

    security_df = build_security_features(records)
    security_df["target_suspicious_movement"] = (security_df["distance_to_installation"] > 40).astype(int)
    security_df["target_tamper_event"] = (security_df["tamper_events"] > 0).astype(int)
    security_df["target_asset_security_risk"] = (
        (security_df["enclosure_opened"] == 1)
        | (security_df["identity_mismatch"] == 1)
        | (security_df["movement_then_gap"] == 1)
    ).astype(int)

    maintenance_features = [
        "battery_voltage_trend",
        "battery_voltage_volatility",
        "soc_drop",
        "battery_temp_trend",
        "max_battery_temp",
        "charge_duration_seconds",
        "discharge_duration_seconds",
        "solar_load_ratio",
        "health_delta",
        "error_count",
        "reset_frequency",
        "sensor_availability",
        "connectivity_gap",
        "device_temp_internal",
        "solar_controller_instability",
        "overload_signal",
        "short_circuit_signal",
        "electrical_stability",
    ]
    security_features = [
        "distance_to_installation",
        "geofence_exit",
        "movement_speed",
        "movement_duration",
        "movement_events",
        "enclosure_opened",
        "tamper_events",
        "impact_or_tilt",
        "movement_then_gap",
        "gap_after_opening",
        "device_silence_duration",
        "identity_mismatch",
        "sim_or_operator_change",
        "post_security_reset",
        "security_sensor_missing",
        "abnormal_usage",
        "repeated_suspicious_events",
    ]

    maintenance_model = RandomForestClassifier(n_estimators=25, random_state=7)
    maintenance_model.fit(maintenance_df[maintenance_features], maintenance_df["target_technical_anomaly"])
    maintenance_predictions = maintenance_model.predict(maintenance_df[maintenance_features])

    security_model = RandomForestClassifier(n_estimators=25, random_state=7)
    security_model.fit(security_df[security_features], security_df["target_asset_security_risk"])
    security_predictions = security_model.predict(security_df[security_features])

    maintenance_accuracy = accuracy_score(maintenance_df["target_technical_anomaly"], maintenance_predictions)
    security_accuracy = accuracy_score(security_df["target_asset_security_risk"], security_predictions)

    joblib.dump(maintenance_model, output_dir / "maintenance_model.joblib")
    joblib.dump(security_model, output_dir / "security_model.joblib")
    joblib.dump(maintenance_features, output_dir / "maintenance_features.joblib")
    joblib.dump(security_features, output_dir / "security_features.joblib")

    metadata = {
        "maintenance": {
            "model_version": "synthetic-v1",
            "features": maintenance_features,
            "accuracy": round(float(maintenance_accuracy), 4),
            "synthetic_data": True,
            "intended_use": "local demonstration only",
            "limitations": ["trained on synthetic telemetry only"],
        },
        "security": {
            "model_version": "synthetic-v1",
            "features": security_features,
            "accuracy": round(float(security_accuracy), 4),
            "synthetic_data": True,
            "intended_use": "local demonstration only",
            "limitations": ["trained on synthetic telemetry only"],
        },
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata
