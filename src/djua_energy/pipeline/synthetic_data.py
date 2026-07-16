from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any


@dataclass
class ScenarioConfig:
    name: str
    duration: int = 24
    interval_seconds: int = 1800


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
                    payload = self._build_payload(kit_index, scenario, step, base_time)
                    records.append(payload)
        return records

    def _build_payload(self, kit_index: int, scenario: str, step: int, base_time: int) -> dict[str, Any]:
        soc = 95 - step * 0.6
        battery_voltage = 13.4 - (0.01 * step)
        temperature = 32 + (0.1 * step)
        solar_power = 120 + 5 * math.sin(step / 3)
        load_power = 55 + 2 * math.cos(step / 4)
        movement = 0
        tamper = 0
        enclosure_opened = False
        identity_mismatch = False
        connectivity_gap = 0
        connection_status = "connected"
        gps_accuracy = 3.2
        if scenario == "progressive_battery_degradation":
            soc = max(20, 95 - step * 1.5)
            battery_voltage -= 0.03 * step
        elif scenario == "battery_overheating":
            temperature += 12 + (step % 3) * 0.8
        elif scenario == "suspicious_movement":
            movement = 1 if step % 5 == 0 else 0
            gps_accuracy = 4.8 if movement else 2.9
        elif scenario == "tamper_attempt":
            tamper = 1 if step % 7 == 0 else 0
            enclosure_opened = tamper == 1
        elif scenario == "weak_connectivity":
            solar_power *= 0.6
            connectivity_gap = 120
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
            connectivity_gap = 300
            connection_status = "disconnected"
            gps_accuracy = 4.0

        payload = {
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
            "battery_voltage_v": round(battery_voltage, 2),
            "battery_current_a": round(3.0 + (step % 4) * 0.1, 2),
            "battery_power_w": round(battery_voltage * (3.0 + (step % 4) * 0.1), 2),
            "battery_temperature_c": round(temperature, 2),
            "state_of_charge_pct": round(soc, 2),
            "state_of_health_pct": round(100 - step * 0.08, 2),
            "battery_cycle_count": 120 + step,
            "battery_capacity_ah": 80.0,
            "battery_remaining_capacity_ah": round(max(10, 80 - step * 0.3), 2),
            "charging_status": "charging" if step % 2 == 0 else "idle",
            "charge_duration_seconds": 6000 if step % 2 == 0 else 0,
            "discharge_duration_seconds": 0 if step % 2 == 0 else 1800,
            "battery_error_code": "NONE" if step % 10 else "BATT_TEMP_HIGH",
            "battery_controller_status": "ok",
            "solar_voltage_v": 22.0,
            "solar_current_a": round(4.5 + 0.02 * (step % 6), 2),
            "solar_power_w": round(solar_power, 2),
            "energy_generated_wh": round(1200 + step * 20, 2),
            "panel_temperature_c": round(temperature + 4, 2),
            "solar_controller_status": "ok",
            "solar_error_code": "NONE",
            "load_voltage_v": 12.0,
            "load_current_a": round(1.2 + 0.03 * (step % 5), 2),
            "load_power_w": round(load_power, 2),
            "energy_consumed_wh": round(600 + step * 25, 2),
            "peak_load_power_w": round(load_power + 10, 2),
            "load_status": "ok",
            "overload_detected": False,
            "short_circuit_detected": False,
            "output_enabled": True,
            "abnormal_consumption_detected": False,
            "latitude": 48.8566 + 0.0001 * kit_index,
            "longitude": 2.3522 + 0.0002 * kit_index,
            "gps_accuracy_m": gps_accuracy,
            "gps_fix_status": "fixed",
            "altitude_m": 35.0,
            "speed_mps": 0.0,
            "heading_deg": 0.0,
            "distance_from_installation_m": 0.0,
            "authorized_radius_m": 50.0,
            "movement_detected": bool(movement),
            "movement_duration_seconds": 60 if movement else 0,
            "movement_event_count": 1 if movement else 0,
            "tilt_angle_deg": 0.0,
            "impact_detected": False,
            "geofence_status": "inside",
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
            "signal_strength_dbm": -68,
            "network_operator": "synthetic-op",
            "sim_identifier_hash": f"sim-{kit_index}",
            "network_cell_id_hash": f"cell-{kit_index}",
            "last_successful_sync_at": str(base_time),
            "queued_messages": 0,
            "retry_count": 0,
            "connectivity_gap_seconds": connectivity_gap,
            "packet_loss_ratio": 0.0,
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
        return payload

    def save(self, records: list[dict[str, Any]], output_path: str | Path | None = None) -> Path:
        output_path = Path(output_path or "data/generated/synthetic_telemetry.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return output_path
