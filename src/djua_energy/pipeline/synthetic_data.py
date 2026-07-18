from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

import pandas as pd


@dataclass
class ScenarioConfig:
    name: str
    duration: int = 24
    interval_seconds: int = 1800


REGION_PROFILES = [
    {
        "region": "sahel_north",
        "latitude": 14.7167,
        "longitude": -17.4677,
        "ambient_base_c": 36.0,
        "humidity_base_pct": 32.0,
        "irradiance_base": 900.0,
        "network_bias": "medium",
        "risk_zone_bias": "medium",
    },
    {
        "region": "coastal_humid",
        "latitude": 5.3600,
        "longitude": -4.0083,
        "ambient_base_c": 30.0,
        "humidity_base_pct": 82.0,
        "irradiance_base": 650.0,
        "network_bias": "good",
        "risk_zone_bias": "medium",
    },
    {
        "region": "forest_south",
        "latitude": 6.1375,
        "longitude": 1.2123,
        "ambient_base_c": 28.0,
        "humidity_base_pct": 88.0,
        "irradiance_base": 580.0,
        "network_bias": "weak",
        "risk_zone_bias": "high",
    },
    {
        "region": "highland_central",
        "latitude": 9.3077,
        "longitude": 2.3158,
        "ambient_base_c": 24.0,
        "humidity_base_pct": 62.0,
        "irradiance_base": 760.0,
        "network_bias": "medium",
        "risk_zone_bias": "low",
    },
    {
        "region": "urban_periurban",
        "latitude": 6.5244,
        "longitude": 3.3792,
        "ambient_base_c": 31.0,
        "humidity_base_pct": 70.0,
        "irradiance_base": 720.0,
        "network_bias": "good",
        "risk_zone_bias": "high",
    },
]

SEASON_PROFILES = {
    "dry": {"temp_delta": 4.0, "humidity_delta": -18.0, "irradiance_factor": 1.15},
    "rainy": {"temp_delta": -2.0, "humidity_delta": 15.0, "irradiance_factor": 0.62},
    "harmattan": {"temp_delta": 1.0, "humidity_delta": -25.0, "irradiance_factor": 0.82},
    "transition": {"temp_delta": 0.0, "humidity_delta": 0.0, "irradiance_factor": 1.0},
}

USAGE_PROFILES = {
    "low": {"load_factor": 0.75, "soc_penalty": 0.2},
    "normal": {"load_factor": 1.0, "soc_penalty": 0.55},
    "intensive": {"load_factor": 1.35, "soc_penalty": 1.0},
}

INSTALLATION_TYPES = {
    "household_rooftop": {"solar_factor": 1.0, "temp_delta": 0.0},
    "ground_mount": {"solar_factor": 1.08, "temp_delta": -0.8},
    "kiosk_shared": {"solar_factor": 0.92, "temp_delta": 1.2},
    "mobile_asset": {"solar_factor": 0.85, "temp_delta": 1.5},
}

NETWORK_GAP_SECONDS = {"good": 0, "medium": 70, "weak": 180}
RISK_ZONE_SCORES = {"low": 0, "medium": 1, "high": 2}


class SyntheticTelemetryGenerator:
    def __init__(self, seed: int = 42, num_kits: int = 3):
        self.seed = seed
        self.num_kits = num_kits
        self.rng = Random(seed)

    def generate(self, scenarios: list[str] | None = None, duration_hours: int = 12) -> list[dict[str, Any]]:
        scenarios = scenarios or [
            "normal_operation",
            "progressive_battery_degradation",
            "battery_overheating",
            "suspicious_movement",
            "tamper_attempt",
        ]
        records: list[dict[str, Any]] = []
        for kit_index in range(self.num_kits):
            for scenario in scenarios:
                for step in range(duration_hours * 2):
                    base_time = 1700000000 + (kit_index * 6000) + step * 1800
                    records.append(self._build_payload(kit_index, scenario, step, base_time))
        return records

    def _build_payload(self, kit_index: int, scenario: str, step: int, base_time: int) -> dict[str, Any]:
        context = _context_for(kit_index, step, scenario, self.rng)
        soc = 95 - step * 0.6 - context["battery_age_months"] * 0.04
        battery_voltage = 13.4 - (0.01 * step) - context["battery_age_months"] * 0.004
        temperature = 32 + (0.1 * step) + max(0, context["ambient_temperature_c"] - 32) * 0.08
        solar_power = 120 + 5 * math.sin(step / 3)
        solar_power *= max(0.08, context["solar_irradiance_w_m2"] / 750.0)
        load_power = 55 + 2 * math.cos(step / 4)
        load_power *= USAGE_PROFILES[context["usage_profile"]]["load_factor"]
        movement = 0
        tamper = 0
        enclosure_opened = False
        identity_mismatch = False
        connectivity_gap = NETWORK_GAP_SECONDS[context["network_quality"]]
        connection_status = "connected" if connectivity_gap < 60 else "degraded"
        gps_accuracy = 4.8 if context["network_quality"] == "weak" else 3.2

        if scenario == "progressive_battery_degradation":
            soc = max(20, 95 - step * 1.5 - context["battery_age_months"] * 0.08)
            battery_voltage -= 0.03 * step
        elif scenario == "battery_overheating":
            temperature += 12 + (step % 3) * 0.8
        elif scenario == "rapid_discharge":
            soc = max(15, soc - step * 1.8)
            load_power *= 1.35
        elif scenario == "unstable_voltage":
            battery_voltage -= 0.15 if step % 2 else -0.08
        elif scenario == "low_solar_input":
            solar_power *= 0.42
        elif scenario == "suspicious_movement":
            movement = 1 if step % 5 == 0 else 0
            gps_accuracy = 4.8 if movement else gps_accuracy
        elif scenario == "tamper_attempt":
            tamper = 1 if step % 7 == 0 else 0
            enclosure_opened = tamper == 1
        elif scenario == "weak_connectivity":
            solar_power *= 0.6
            connectivity_gap = max(connectivity_gap, 120)
            connection_status = "degraded"
        elif scenario == "geofence_exit":
            movement = 1
            gps_accuracy = 5.1
        elif scenario == "enclosure_opening":
            enclosure_opened = True
            tamper = 1
        elif scenario == "identity_mismatch":
            identity_mismatch = True
        elif scenario == "movement_then_connectivity_loss":
            movement = 1
            connectivity_gap = max(connectivity_gap, 300)
            connection_status = "disconnected"
            gps_accuracy = 5.0

        return {
            "message_id": f"msg-{kit_index}-{step}-{self.rng.randint(1000, 9999)}",
            "schema_version": "1.0",
            "message_type": "telemetry",
            "device_id": f"device-{kit_index}",
            "kit_id": f"kit-{kit_index}",
            "serial_number": f"SN-{kit_index:03d}",
            "device_model": "djua-solar-v1",
            "hardware_revision": "rev-a",
            "firmware_version": "1.0.0",
            "boot_id": f"boot-{kit_index}-{step}",
            "event_time": str(base_time),
            "ingestion_time": str(base_time + 60),
            "sequence_number": step + 1,
            "sampling_interval_seconds": 1800,
            "synthetic_data": True,
            "scenario": scenario,
            "metadata": {"source": "synthetic"},
            **context,
            "battery_voltage_v": round(battery_voltage, 2),
            "battery_current_a": round(3.0 + (step % 4) * 0.1, 2),
            "battery_power_w": round(battery_voltage * (3.0 + (step % 4) * 0.1), 2),
            "battery_temperature_c": round(temperature, 2),
            "state_of_charge_pct": round(max(10, soc), 2),
            "state_of_health_pct": round(max(55, 100 - step * 0.08 - context["battery_age_months"] * 0.35), 2),
            "battery_cycle_count": 120 + step + context["battery_age_months"] * 8,
            "battery_capacity_ah": 80.0,
            "battery_remaining_capacity_ah": round(max(10, 80 - step * 0.3), 2),
            "charging_status": "charging" if step % 2 == 0 else "idle",
            "charge_duration_seconds": 6000 if step % 2 == 0 else 0,
            "discharge_duration_seconds": 0 if step % 2 == 0 else 1800,
            "battery_error_code": "NONE" if step % 10 else "BATT_TEMP_HIGH",
            "battery_controller_status": "ok",
            "solar_voltage_v": 22.0,
            "solar_current_a": round(max(0.1, solar_power / 22.0), 2),
            "solar_power_w": round(max(0, solar_power), 2),
            "energy_generated_wh": round(1200 + step * max(1, solar_power / 6), 2),
            "panel_temperature_c": round(temperature + 4, 2),
            "solar_controller_status": "ok",
            "solar_error_code": "NONE",
            "load_voltage_v": 12.0,
            "load_current_a": round(max(0.1, load_power / 12.0), 2),
            "load_power_w": round(load_power, 2),
            "energy_consumed_wh": round(600 + step * max(1, load_power / 2), 2),
            "peak_load_power_w": round(load_power + 10, 2),
            "load_status": "ok",
            "overload_detected": False,
            "short_circuit_detected": False,
            "output_enabled": True,
            "abnormal_consumption_detected": context["usage_profile"] == "intensive",
            "gps_accuracy_m": gps_accuracy,
            "gps_fix_status": "fixed",
            "altitude_m": 35.0,
            "speed_mps": 0.4 if movement else 0.0,
            "heading_deg": 0.0,
            "distance_from_installation_m": 60.0 if movement else 0.0,
            "authorized_radius_m": 50.0,
            "movement_detected": bool(movement),
            "movement_duration_seconds": 60 if movement else 0,
            "movement_event_count": 1 if movement else 0,
            "tilt_angle_deg": 0.0,
            "impact_detected": False,
            "geofence_status": "outside" if movement else "inside",
            "tamper_detected": bool(tamper),
            "enclosure_opened": bool(enclosure_opened),
            "cable_disconnection_detected": False,
            "unauthorized_power_cycle_detected": False,
            "security_event_code": "NONE",
            "security_event_time": None,
            "tamper_sensor_status": "ok",
            "enclosure_sensor_status": "ok",
            "asset_lock_status": "locked",
            "identity_mismatch_detected": bool(identity_mismatch),
            "connectivity_type": "lte",
            "connection_status": connection_status,
            "signal_strength_dbm": -92 if context["network_quality"] == "weak" else -68,
            "network_operator": "synthetic-op",
            "sim_identifier_hash": f"sim-{kit_index}",
            "network_cell_id_hash": f"cell-{kit_index}",
            "last_successful_sync_at": str(base_time),
            "queued_messages": 0,
            "retry_count": 0,
            "connectivity_gap_seconds": connectivity_gap,
            "packet_loss_ratio": 0.18 if context["network_quality"] == "weak" else 0.0,
            "data_usage_bytes": 512,
            "is_buffered_message": False,
            "buffered_at": None,
            "transmission_attempt": 1,
            "device_uptime_seconds": 100000 + step * 10,
            "device_temperature_c": round(temperature + 1.5, 2),
            "cpu_usage_pct": 18 + (step % 4) * 3,
            "memory_usage_pct": 34 + (step % 3) * 4,
            "storage_usage_pct": 20 + (step % 7),
            "reset_reason": "NONE",
            "reset_count": 0,
            "watchdog_reset_count": 0,
            "brownout_detected": False,
            "device_error_code": "NONE",
            "internal_clock_status": "ok",
            "local_storage_status": "ok",
            "sensor_status": "ok",
            "measurement_quality": "good",
            "sensor_calibration_version": "1.0",
            "calibration_date": "2026-01-01",
            "missing_measurement_count": 0,
            "invalid_measurement_count": 0,
            "sensor_failure_detected": False,
            "quality_flag": "ok",
            "data_completeness_pct": 100.0,
        }

    def save(self, records: list[dict[str, Any]], output_path: str | Path | None = None) -> Path:
        output_path = Path(output_path or "data/generated/synthetic_telemetry.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return output_path


def _context_for(device_idx: int, sample_idx: int, scenario: str, rng: Random) -> dict[str, Any]:
    region = REGION_PROFILES[device_idx % len(REGION_PROFILES)]
    season_name = list(SEASON_PROFILES)[(device_idx + sample_idx) % len(SEASON_PROFILES)]
    season = SEASON_PROFILES[season_name]
    usage_name = list(USAGE_PROFILES)[(device_idx + sample_idx + len(scenario)) % len(USAGE_PROFILES)]
    installation_name = list(INSTALLATION_TYPES)[(device_idx + sample_idx * 2) % len(INSTALLATION_TYPES)]
    installation = INSTALLATION_TYPES[installation_name]
    day_period = "night" if sample_idx % 4 == 0 else "day"
    day_factor = 0.08 if day_period == "night" else 1.0
    ambient_temperature = region["ambient_base_c"] + season["temp_delta"] + installation["temp_delta"] + rng.uniform(-2.5, 2.5)
    humidity = max(15.0, min(98.0, region["humidity_base_pct"] + season["humidity_delta"] + rng.uniform(-8, 8)))
    solar_irradiance = max(
        20.0,
        region["irradiance_base"] * season["irradiance_factor"] * day_factor * installation["solar_factor"] + rng.uniform(-35, 35),
    )
    network_quality = str(region["network_bias"])
    if scenario in {"connectivity_loss", "weak_connectivity", "movement_then_connectivity_loss"} or sample_idx % 17 == 0:
        network_quality = "weak"
    elif sample_idx % 11 == 0 and network_quality == "good":
        network_quality = "medium"
    security_risk_zone = "high" if scenario in {"movement_and_tampering", "tamper_attempt"} else str(region["risk_zone_bias"])
    battery_age_months = 3 + ((device_idx * 7) % 54)
    return {
        "region": region["region"],
        "season": season_name,
        "day_period": day_period,
        "ambient_temperature_c": round(ambient_temperature, 2),
        "humidity_pct": round(humidity, 2),
        "solar_irradiance_w_m2": round(solar_irradiance, 2),
        "network_quality": network_quality,
        "installation_type": installation_name,
        "battery_age_months": battery_age_months,
        "usage_profile": usage_name,
        "security_risk_zone": security_risk_zone,
        "latitude": round(region["latitude"] + device_idx * 0.001 + rng.uniform(-0.01, 0.01), 6),
        "longitude": round(region["longitude"] + device_idx * 0.001 + rng.uniform(-0.01, 0.01), 6),
    }


def dataset_row_to_telemetry_record(row: dict[str, Any] | pd.Series) -> dict[str, Any]:
    if isinstance(row, pd.Series):
        row_data = row.to_dict()
    else:
        row_data = dict(row)

    scenario = str(row_data.get("scenario", "normal_operation"))
    device_id = str(row_data.get("device_id", "device-1"))
    device_index = int(device_id.split("-")[-1]) if device_id.split("-")[-1].isdigit() else 1
    sample_id = str(row_data.get("sample_id", "sample-1"))
    parts = sample_id.split("-")
    sequence_number = int(parts[-1]) if parts and parts[-1].isdigit() else 1
    movement_detected = int(row_data.get("movement_detected", 0))
    tamper_detected = int(row_data.get("tamper_detected", 0))
    enclosure_opened = int(row_data.get("enclosure_opened", 0))
    connectivity_gap = int(row_data.get("connectivity_gap_seconds", 0))
    battery_voltage = float(row_data.get("battery_voltage_v", 13.2))
    battery_temperature = float(row_data.get("battery_temperature_c", 31.5))
    state_of_charge = float(row_data.get("state_of_charge_pct", 88.0))
    battery_age = int(row_data.get("battery_age_months", 12))

    if scenario == "overheating":
        battery_error_code = "BATT_TEMP_HIGH"
        charge_duration_seconds = 3600
        discharge_duration_seconds = 600
    elif scenario == "connectivity_loss":
        battery_error_code = "NONE"
        charge_duration_seconds = 0
        discharge_duration_seconds = 1800
    elif scenario == "movement_and_tampering":
        battery_error_code = "NONE"
        charge_duration_seconds = 2400
        discharge_duration_seconds = 900
    elif scenario in {"battery_degradation", "low_solar_input"}:
        battery_error_code = "NONE"
        charge_duration_seconds = 3000
        discharge_duration_seconds = 1200
    else:
        battery_error_code = "NONE"
        charge_duration_seconds = 6000
        discharge_duration_seconds = 0

    reset_count = 1 if scenario in {"movement_and_tampering", "connectivity_loss"} else 0
    sensor_failure_detected = 1 if scenario == "connectivity_loss" else 0
    identity_mismatch = 1 if scenario == "movement_and_tampering" else 0
    impact_detected = 1 if scenario == "movement_and_tampering" else 0

    return {
        "message_id": sample_id,
        "schema_version": "1.0",
        "message_type": "telemetry",
        "device_id": device_id,
        "kit_id": device_id,
        "serial_number": f"SN-{device_index:03d}",
        "event_time": str(1700000000 + device_index * 1000 + sequence_number),
        "sequence_number": sequence_number,
        "region": str(row_data.get("region", "centre")),
        "season": str(row_data.get("season", "dry")),
        "day_period": str(row_data.get("day_period", "day")),
        "ambient_temperature_c": float(row_data.get("ambient_temperature_c", 28.0)),
        "humidity_pct": float(row_data.get("humidity_pct", 55.0)),
        "solar_irradiance_w_m2": float(row_data.get("solar_irradiance_w_m2", 750.0)),
        "network_quality": str(row_data.get("network_quality", "good")),
        "installation_type": str(row_data.get("installation_type", "household_rooftop")),
        "battery_age_months": battery_age,
        "usage_profile": str(row_data.get("usage_profile", "normal")),
        "security_risk_zone": str(row_data.get("security_risk_zone", "medium")),
        "latitude": float(row_data.get("latitude", 0.0)),
        "longitude": float(row_data.get("longitude", 0.0)),
        "battery_voltage_v": round(battery_voltage, 2),
        "battery_current_a": 2.5,
        "battery_power_w": round(battery_voltage * 2.5, 2),
        "battery_temperature_c": round(battery_temperature, 2),
        "state_of_charge_pct": round(state_of_charge, 2),
        "state_of_health_pct": round(max(55.0, 98.0 - battery_age * 0.45), 2),
        "battery_error_code": battery_error_code,
        "charge_duration_seconds": float(charge_duration_seconds),
        "discharge_duration_seconds": float(discharge_duration_seconds),
        "solar_power_w": round(float(row_data.get("solar_power_w", 120.0)), 2),
        "load_power_w": round(float(row_data.get("load_power_w", 55.0)), 2),
        "solar_error_code": "NONE",
        "overload_detected": False,
        "short_circuit_detected": False,
        "gps_accuracy_m": float(row_data.get("gps_accuracy_m", 5.0 if movement_detected else 3.0)),
        "movement_detected": bool(movement_detected),
        "movement_duration_seconds": 60 if movement_detected else 0,
        "movement_event_count": 1 if movement_detected else 0,
        "tamper_detected": bool(tamper_detected),
        "enclosure_opened": bool(enclosure_opened),
        "impact_detected": bool(impact_detected),
        "distance_from_installation_m": 60.0 if movement_detected else 0.0,
        "geofence_status": "outside" if movement_detected else "inside",
        "speed_mps": 0.4 if movement_detected else 0.0,
        "connectivity_gap_seconds": connectivity_gap,
        "connection_status": "disconnected" if connectivity_gap > 250 else ("degraded" if connectivity_gap > 50 else "connected"),
        "device_temperature_c": round(battery_temperature + 1.2, 2),
        "identity_mismatch_detected": bool(identity_mismatch),
        "network_operator": "synthetic-op",
        "reset_count": reset_count,
        "missing_measurement_count": 0,
        "sensor_failure_detected": bool(sensor_failure_detected),
        "abnormal_consumption_detected": bool(scenario in {"connectivity_loss"} or row_data.get("usage_profile") == "intensive"),
        "synthetic_data": True,
        "scenario": scenario,
    }


def generate_mvp_dataset(
    num_devices: int = 50,
    records_per_scenario: int = 34,
    output_path: str | Path | None = None,
    target_rows: int | None = 10000,
) -> pd.DataFrame:
    scenario_profiles = [
        {"scenario": "normal_operation", "battery_voltage_v": 13.2, "battery_temperature_c": 31.5, "state_of_charge_pct": 88.0, "movement_detected": 0, "tamper_detected": 0, "enclosure_opened": 0, "connectivity_gap_seconds": 0, "solar_power_w": 120.0, "label_maintenance": 0, "label_security": 0},
        {"scenario": "battery_degradation", "battery_voltage_v": 11.8, "battery_temperature_c": 34.0, "state_of_charge_pct": 62.0, "movement_detected": 0, "tamper_detected": 0, "enclosure_opened": 0, "connectivity_gap_seconds": 0, "solar_power_w": 108.0, "label_maintenance": 1, "label_security": 0},
        {"scenario": "overheating", "battery_voltage_v": 12.5, "battery_temperature_c": 47.0, "state_of_charge_pct": 78.0, "movement_detected": 0, "tamper_detected": 0, "enclosure_opened": 0, "connectivity_gap_seconds": 0, "solar_power_w": 95.0, "label_maintenance": 1, "label_security": 0},
        {"scenario": "movement_and_tampering", "battery_voltage_v": 13.0, "battery_temperature_c": 33.0, "state_of_charge_pct": 84.0, "movement_detected": 1, "tamper_detected": 1, "enclosure_opened": 1, "connectivity_gap_seconds": 45, "solar_power_w": 110.0, "label_maintenance": 0, "label_security": 1},
        {"scenario": "connectivity_loss", "battery_voltage_v": 12.9, "battery_temperature_c": 32.5, "state_of_charge_pct": 79.0, "movement_detected": 0, "tamper_detected": 0, "enclosure_opened": 0, "connectivity_gap_seconds": 320, "solar_power_w": 70.0, "label_maintenance": 1, "label_security": 1},
        {"scenario": "low_solar_input", "battery_voltage_v": 12.2, "battery_temperature_c": 32.0, "state_of_charge_pct": 74.0, "movement_detected": 0, "tamper_detected": 0, "enclosure_opened": 0, "connectivity_gap_seconds": 0, "solar_power_w": 40.0, "label_maintenance": 1, "label_security": 0},
    ]
    rng = Random(20260717)
    rows: list[dict[str, Any]] = []
    for device_idx in range(num_devices):
        battery_age_months = 3 + ((device_idx * 7) % 54)
        for profile in scenario_profiles:
            for sample_idx in range(records_per_scenario):
                if target_rows is not None and len(rows) >= target_rows:
                    break
                context = _context_for(device_idx, sample_idx, profile["scenario"], rng)
                usage = USAGE_PROFILES[context["usage_profile"]]
                age_voltage_penalty = battery_age_months * 0.006
                ambient_temp_penalty = max(0.0, context["ambient_temperature_c"] - 35.0) * 0.04
                load_power = round((55.0 + (sample_idx % 6) * 2.5) * usage["load_factor"], 2)
                solar_power = round(profile["solar_power_w"] * (context["solar_irradiance_w_m2"] / 750.0) + sample_idx * 0.6 - device_idx * 0.15, 2)
                if profile["scenario"] == "low_solar_input":
                    solar_power = round(solar_power * 0.55, 2)
                connectivity_gap = profile["connectivity_gap_seconds"] + sample_idx * 3 + NETWORK_GAP_SECONDS[context["network_quality"]]
                row = {
                    "sample_id": f"sample-{device_idx + 1}-{profile['scenario']}-{sample_idx + 1}",
                    "device_id": f"device-{device_idx + 1}",
                    "scenario": profile["scenario"],
                    **context,
                    "battery_voltage_v": round(profile["battery_voltage_v"] + (sample_idx % 5) * 0.05 + device_idx * 0.005 - age_voltage_penalty, 2),
                    "battery_temperature_c": round(profile["battery_temperature_c"] + sample_idx * 0.08 + ambient_temp_penalty, 2),
                    "state_of_charge_pct": round(max(15, profile["state_of_charge_pct"] - usage["soc_penalty"] * sample_idx - battery_age_months * 0.08), 2),
                    "movement_detected": profile["movement_detected"],
                    "tamper_detected": profile["tamper_detected"],
                    "enclosure_opened": profile["enclosure_opened"],
                    "connectivity_gap_seconds": connectivity_gap,
                    "solar_power_w": max(0.0, solar_power),
                    "load_power_w": load_power,
                    "gps_accuracy_m": 8.0 if context["network_quality"] == "weak" else 4.0,
                    "label_maintenance": profile["label_maintenance"],
                    "label_security": profile["label_security"],
                    "notes": f"MVP v2 scenario for {profile['scenario']} in {context['region']} during {context['season']}",
                }
                rows.append(row)
            if target_rows is not None and len(rows) >= target_rows:
                break
        if target_rows is not None and len(rows) >= target_rows:
            break

    df = pd.DataFrame(rows)
    output_path = Path(output_path or "data/generated/mvp_dataset.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df
