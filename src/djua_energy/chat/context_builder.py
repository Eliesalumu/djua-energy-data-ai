from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import dataset_row_to_telemetry_record


DATASET_PATH = Path("data/generated/mvp_dataset.csv")


SCENARIO_LABELS = {
    "normal_operation": "fonctionnement normal",
    "battery_degradation": "degradation batterie",
    "overheating": "surchauffe batterie",
    "movement_and_tampering": "mouvement et tentative de sabotage",
    "connectivity_loss": "perte de connectivite",
    "low_solar_input": "faible production solaire",
}


@dataclass(frozen=True)
class DeviceQuery:
    device_id: str | None
    intent: str


def extract_device_query(message: str) -> DeviceQuery:
    normalized = message.strip().lower()
    match = re.search(r"\bdevice[-_\s]?(\d+)\b", normalized)
    if match:
        return DeviceQuery(device_id=f"device-{int(match.group(1))}", intent="device_diagnosis")
    if "normal" in normalized:
        return DeviceQuery(device_id=None, intent="normal_devices")
    if "critique" in normalized or "critical" in normalized:
        return DeviceQuery(device_id=None, intent="critical_devices")
    return DeviceQuery(device_id=None, intent="fleet_overview")


def load_dataset(dataset_path: str | Path | None = None) -> pd.DataFrame:
    path = Path(dataset_path or DATASET_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Dataset introuvable: {path}")
    return pd.read_csv(path)


def _safe_min(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    return round(float(df[column].min()), 3) if column in df and not df.empty else default


def _safe_max(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    return round(float(df[column].max()), 3) if column in df and not df.empty else default


def _safe_bool_any(df: pd.DataFrame, column: str) -> bool:
    return bool(df[column].max()) if column in df and not df.empty else False


def _device_indicators(device_rows: pd.DataFrame) -> dict[str, Any]:
    day_rows = device_rows[device_rows.get("day_period", "day") == "day"] if "day_period" in device_rows else device_rows
    solar_rows = day_rows if not day_rows.empty else device_rows
    sample = device_rows.iloc[0]
    return {
        "measure_count": int(len(device_rows)),
        "scenario_count": int(device_rows["scenario"].nunique()),
        "region": str(sample.get("region", "n/a")),
        "season": str(sample.get("season", "n/a")),
        "installation_type": str(sample.get("installation_type", "n/a")),
        "usage_profile": str(sample.get("usage_profile", "n/a")),
        "security_risk_zone": str(sample.get("security_risk_zone", "n/a")),
        "battery_age_months": int(sample.get("battery_age_months", 0)),
        "min_battery_voltage_v": _safe_min(device_rows, "battery_voltage_v"),
        "max_battery_temperature_c": _safe_max(device_rows, "battery_temperature_c"),
        "min_state_of_charge_pct": _safe_min(device_rows, "state_of_charge_pct"),
        "min_solar_power_w": _safe_min(solar_rows, "solar_power_w"),
        "max_connectivity_gap_seconds": int(_safe_max(device_rows, "connectivity_gap_seconds")),
        "movement_detected": _safe_bool_any(device_rows, "movement_detected"),
        "tamper_detected": _safe_bool_any(device_rows, "tamper_detected"),
        "enclosure_opened": _safe_bool_any(device_rows, "enclosure_opened"),
    }


def _local_status(indicators: dict[str, Any]) -> str:
    if indicators["enclosure_opened"] or indicators["tamper_detected"]:
        return "critique"
    if indicators["max_battery_temperature_c"] >= 48 and indicators["min_battery_voltage_v"] <= 12.3:
        return "critique"
    if indicators["max_connectivity_gap_seconds"] >= 300:
        return "critique"
    if (
        indicators["max_battery_temperature_c"] >= 45
        or indicators["min_battery_voltage_v"] <= 12.3
        or indicators["min_state_of_charge_pct"] <= 60
        or indicators["min_solar_power_w"] <= 70
    ):
        return "eleve"
    return "normal"


def _detected_cases(device_rows: pd.DataFrame, indicators: dict[str, Any]) -> list[str]:
    cases: list[str] = []
    scenarios = [str(item) for item in device_rows["scenario"].drop_duplicates().tolist()]
    for scenario in scenarios:
        label = SCENARIO_LABELS.get(scenario)
        if label and scenario != "normal_operation":
            cases.append(label)
    if indicators["enclosure_opened"] and "ouverture du boitier" not in cases:
        cases.append("ouverture du boitier")
    if indicators["tamper_detected"] and "tamper detecte" not in cases:
        cases.append("tamper detecte")
    return cases or ["aucun cas critique detecte"]


def _summarize_model_window(
    engine: LocalInferenceEngine,
    scenario_rows: pd.DataFrame,
) -> dict[str, Any]:
    records = [dataset_row_to_telemetry_record(row) for _, row in scenario_rows.iterrows()]
    maintenance = engine.infer_maintenance(records)
    security = engine.infer_security(records)
    return {
        "scenario": str(scenario_rows["scenario"].iloc[0]),
        "scenario_label": SCENARIO_LABELS.get(str(scenario_rows["scenario"].iloc[0]), str(scenario_rows["scenario"].iloc[0])),
        "records": len(records),
        "maintenance": maintenance,
        "security": security,
    }


def build_device_context(
    device_id: str,
    *,
    dataset: pd.DataFrame | None = None,
    engine: LocalInferenceEngine | None = None,
) -> dict[str, Any]:
    df = dataset if dataset is not None else load_dataset()
    if device_id not in df["device_id"].values:
        available = sorted(df["device_id"].unique(), key=lambda value: int(str(value).split("-")[-1]))
        return {
            "found": False,
            "device_id": device_id,
            "available_examples": available[:10],
        }

    local_engine = engine or LocalInferenceEngine("artifacts")
    device_rows = df[df["device_id"] == device_id].copy()
    indicators = _device_indicators(device_rows)
    scenario_predictions = [
        _summarize_model_window(local_engine, scenario_rows)
        for _, scenario_rows in device_rows.groupby("scenario", sort=False)
    ]
    return {
        "found": True,
        "device_id": device_id,
        "global_status": _local_status(indicators),
        "detected_cases": _detected_cases(device_rows, indicators),
        "indicators": indicators,
        "model_predictions": scenario_predictions,
        "data_sources": [
            "data/generated/mvp_dataset.csv",
            "artifacts/maintenance_model.joblib",
            "artifacts/security_model.joblib",
        ],
        "guardrails": {
            "synthetic_data": True,
            "human_review_required": True,
            "do_not_invent": True,
        },
    }


def build_fleet_context(*, dataset: pd.DataFrame | None = None) -> dict[str, Any]:
    df = dataset if dataset is not None else load_dataset()
    devices = sorted(df["device_id"].unique(), key=lambda value: int(str(value).split("-")[-1]))
    summaries = []
    for device_id in devices:
        rows = df[df["device_id"] == device_id]
        indicators = _device_indicators(rows)
        summaries.append({
            "device_id": device_id,
            "global_status": _local_status(indicators),
            "detected_cases": _detected_cases(rows, indicators),
            "indicators": indicators,
        })
    normal_devices = [item["device_id"] for item in summaries if item["global_status"] == "normal"]
    critical_devices = [item["device_id"] for item in summaries if item["global_status"] == "critique"]
    return {
        "device_count": len(devices),
        "normal_devices": normal_devices,
        "critical_devices": critical_devices,
        "examples": summaries[:5],
        "data_source": "data/generated/mvp_dataset.csv",
        "guardrails": {"synthetic_data": True, "do_not_invent": True},
    }

