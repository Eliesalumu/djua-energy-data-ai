from __future__ import annotations

from typing import Any

REQUIRED_FIELDS = {
    "telemetry": {
        "required": [
            "message_id",
            "schema_version",
            "message_type",
            "device_id",
            "kit_id",
            "serial_number",
            "event_time",
            "sequence_number",
            "battery_voltage_v",
            "battery_current_a",
            "battery_power_w",
            "battery_temperature_c",
            "state_of_charge_pct",
            "state_of_health_pct",
        ],
        "optional": [
            "region",
            "season",
            "day_period",
            "ambient_temperature_c",
            "humidity_pct",
            "solar_irradiance_w_m2",
            "network_quality",
            "installation_type",
            "battery_age_months",
            "usage_profile",
            "security_risk_zone",
            "solar_voltage_v",
            "solar_current_a",
            "solar_power_w",
            "energy_generated_wh",
            "panel_temperature_c",
            "load_voltage_v",
            "load_current_a",
            "load_power_w",
            "energy_consumed_wh",
            "latitude",
            "longitude",
            "gps_accuracy_m",
            "movement_detected",
            "tamper_detected",
            "enclosure_opened",
            "connectivity_type",
            "connection_status",
            "device_temperature_c",
            "sensor_status",
        ],
    },
    "location": {
        "required": [
            "message_id",
            "schema_version",
            "message_type",
            "device_id",
            "kit_id",
            "serial_number",
            "event_time",
            "sequence_number",
        ],
        "optional": ["latitude", "longitude", "gps_accuracy_m", "gps_fix_status"],
    },
    "security_event": {
        "required": [
            "message_id",
            "schema_version",
            "message_type",
            "device_id",
            "kit_id",
            "serial_number",
            "event_time",
            "sequence_number",
            "tamper_detected",
            "enclosure_opened",
        ],
        "optional": ["security_event_code", "impact_detected"],
    },
    "device_status": {
        "required": [
            "message_id",
            "schema_version",
            "message_type",
            "device_id",
            "kit_id",
            "serial_number",
            "event_time",
            "sequence_number",
            "connectivity_type",
            "connection_status",
            "device_temperature_c",
        ],
        "optional": ["reset_reason", "cpu_usage_pct", "memory_usage_pct"],
    },
    "diagnostic_event": {
        "required": [
            "message_id",
            "schema_version",
            "message_type",
            "device_id",
            "kit_id",
            "serial_number",
            "event_time",
            "sequence_number",
            "battery_error_code",
            "device_error_code",
        ],
        "optional": ["security_event_code"],
    },
}


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Valider un payload de télémétrie synthétique."""
    errors: list[str] = []
    message_type = payload.get("message_type")
    if not message_type:
        return {"valid": False, "errors": ["message_type is required"]}

    spec = REQUIRED_FIELDS.get(message_type)
    if spec is None:
        return {"valid": False, "errors": [f"unsupported message_type: {message_type}"]}

    for field in spec["required"]:
        if payload.get(field) is None or payload.get(field) == "":
            errors.append(f"missing required field: {field}")

    if message_type == "location":
        has_coords = bool(payload.get("latitude") is not None and payload.get("longitude") is not None)
        if has_coords and payload.get("gps_accuracy_m") is None:
            errors.append("gps_accuracy_m is required when coordinates are provided")

    if message_type == "telemetry":
        if payload.get("battery_voltage_v", 0) <= 0:
            errors.append("battery_voltage_v must be positive")
        if payload.get("state_of_charge_pct", 0) < 0 or payload.get("state_of_charge_pct", 0) > 100:
            errors.append("state_of_charge_pct must be in [0, 100]")

    return {"valid": not errors, "errors": errors}
