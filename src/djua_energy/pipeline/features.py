from __future__ import annotations

from typing import Any

import pandas as pd


def _series(df: pd.DataFrame, column: str, default: Any) -> pd.Series:
    if column in df:
        return df[column]
    return pd.Series([default] * len(df), index=df.index)


def build_maintenance_features(records: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    df = df.sort_values(["device_id", "event_time"]).copy()
    df["event_time"] = pd.to_numeric(df["event_time"], errors="coerce")
    df = df.fillna(0)

    grouped = df.groupby("device_id", sort=False)
    df["battery_voltage_trend"] = grouped["battery_voltage_v"].diff()
    df["battery_voltage_volatility"] = grouped["battery_voltage_v"].rolling(3).std().reset_index(level=0, drop=True)
    df["soc_drop"] = grouped["state_of_charge_pct"].diff().fillna(0)
    df["battery_temp_trend"] = grouped["battery_temperature_c"].diff()
    df["max_battery_temp"] = grouped["battery_temperature_c"].transform("max")
    df["charge_duration_seconds"] = _series(df, "charge_duration_seconds", 0).astype(float)
    df["discharge_duration_seconds"] = _series(df, "discharge_duration_seconds", 0).astype(float)
    df["solar_load_ratio"] = _series(df, "solar_power_w", 0).astype(float) / (
        _series(df, "load_power_w", 0).astype(float) + 1e-6
    )
    df["health_delta"] = grouped["state_of_health_pct"].diff().fillna(0)
    df["error_count"] = _series(df, "battery_error_code", "NONE").apply(lambda x: 1 if str(x) != "NONE" else 0)
    df["reset_count"] = _series(df, "reset_count", 0).astype(float)
    df["reset_frequency"] = grouped["reset_count"].diff().fillna(0)
    df["sensor_availability"] = 1 - (_series(df, "missing_measurement_count", 0).astype(float) / 10.0)
    df["connectivity_gap"] = _series(df, "connectivity_gap_seconds", 0).astype(float)
    df["device_temp_internal"] = _series(df, "device_temperature_c", 0).astype(float)
    df["solar_controller_instability"] = (_series(df, "solar_error_code", "NONE") != "NONE").astype(int)
    df["overload_signal"] = _series(df, "overload_detected", False).astype(int)
    df["short_circuit_signal"] = _series(df, "short_circuit_detected", False).astype(int)
    df["electrical_stability"] = 1 - (df["battery_voltage_volatility"] / 5.0)
    df["ambient_temperature"] = _series(df, "ambient_temperature_c", 0).astype(float)
    df["humidity_pct"] = _series(df, "humidity_pct", 0).astype(float)
    df["solar_irradiance"] = _series(df, "solar_irradiance_w_m2", 0).astype(float)
    df["battery_age_months"] = _series(df, "battery_age_months", 0).astype(float)
    df["night_operation"] = (_series(df, "day_period", "") == "night").astype(int)
    df["usage_intensity"] = _series(df, "usage_profile", "normal").map({"low": 0.5, "normal": 1.0, "intensive": 1.5}).fillna(1.0)
    df["network_quality_score"] = _series(df, "network_quality", "medium").map({"good": 0.0, "medium": 0.5, "weak": 1.0}).fillna(0.5)
    df["season_rainy"] = (_series(df, "season", "") == "rainy").astype(int)

    feature_columns = [
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
        "ambient_temperature",
        "humidity_pct",
        "solar_irradiance",
        "battery_age_months",
        "night_operation",
        "usage_intensity",
        "network_quality_score",
        "season_rainy",
    ]
    df[feature_columns] = df[feature_columns].astype(float)
    return df


def build_security_features(records: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    df = df.sort_values(["device_id", "event_time"]).copy()
    df["event_time"] = pd.to_numeric(df["event_time"], errors="coerce")
    df = df.fillna(0)
    df["distance_to_installation"] = _series(df, "distance_from_installation_m", 0).astype(float)
    df["geofence_exit"] = (_series(df, "geofence_status", "inside") != "inside").astype(int)
    df["movement_speed"] = _series(df, "speed_mps", 0).astype(float)
    df["movement_duration"] = _series(df, "movement_duration_seconds", 0).astype(float)
    df["movement_events"] = _series(df, "movement_event_count", 0).astype(float)
    df["enclosure_opened"] = _series(df, "enclosure_opened", False).astype(int)
    df["tamper_detected"] = _series(df, "tamper_detected", False).astype(int)
    df["movement_detected"] = _series(df, "movement_detected", False).astype(int)
    df["connectivity_gap_seconds"] = _series(df, "connectivity_gap_seconds", 0).astype(float)
    df["tamper_events"] = df["tamper_detected"].astype(int)
    df["impact_or_tilt"] = _series(df, "impact_detected", False).astype(int)
    df["movement_then_gap"] = ((df["movement_detected"] == 1) & (df["connectivity_gap_seconds"] > 0)).astype(int)
    df["gap_after_opening"] = ((df["enclosure_opened"] == 1) & (df["connectivity_gap_seconds"] > 0)).astype(int)
    df["device_silence_duration"] = df["connectivity_gap_seconds"].astype(float)
    df["identity_mismatch"] = _series(df, "identity_mismatch_detected", False).astype(int)
    df["sim_or_operator_change"] = (_series(df, "network_operator", "synthetic-op") != "synthetic-op").astype(int)
    df["post_security_reset"] = (_series(df, "reset_count", 0).astype(float) > 0).astype(int)
    df["security_sensor_missing"] = (_series(df, "sensor_failure_detected", False).astype(int) == 1).astype(int)
    df["abnormal_usage"] = _series(df, "abnormal_consumption_detected", False).astype(int)
    df["repeated_suspicious_events"] = (df["tamper_detected"] + df["movement_detected"]).clip(0, 3)
    df["security_risk_zone_score"] = _series(df, "security_risk_zone", "medium").map({"low": 0.0, "medium": 0.5, "high": 1.0}).fillna(0.5)
    df["network_quality_score"] = _series(df, "network_quality", "medium").map({"good": 0.0, "medium": 0.5, "weak": 1.0}).fillna(0.5)
    df["mobile_installation"] = (_series(df, "installation_type", "") == "mobile_asset").astype(int)
    df["night_operation"] = (_series(df, "day_period", "") == "night").astype(int)

    feature_columns = [
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
        "security_risk_zone_score",
        "network_quality_score",
        "mobile_installation",
        "night_operation",
    ]
    df[feature_columns] = df[feature_columns].astype(float)
    return df
