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
            "battery_voltage_v",
            "battery_current_a",
            "battery_power_w",
            "state_of_charge_pct",
            "state_of_health_pct",
        ],
        "optional": [
            "region",
            "season",
            "day_period",
            "ambient_temperature_c",
            "humidity_pct",
            "installation_type",
            "battery_age_months",
            "usage_profile",
            "security_risk_zone",
            "charge_duration_seconds",
            "discharge_duration_seconds",
            "solar_voltage_v",
            "solar_current_a",
            "solar_power_w",
            "energy_generated_wh",
            "solar_irradiance_w_m2",
            "panel_temperature_c",
            "solar_error_code",
            "load_voltage_v",
            "load_current_a",
            "load_power_w",
            "energy_consumed_wh",
            "overload_detected",
            "short_circuit_detected",
            "latitude",
            "longitude",
            "gps_accuracy_m",
            "distance_from_installation_m",
            "geofence_status",
            "speed_mps",
            "movement_detected",
            "movement_duration_seconds",
            "movement_event_count",
            "tamper_detected",
            "enclosure_opened",
            "impact_detected",
            "identity_mismatch_detected",
            "connectivity_type",
            "connection_status",
            "network_quality",
            "connectivity_gap_seconds",
            "network_operator",
            "device_temperature_c",
            "reset_count",
            "missing_measurement_count",
            "sensor_status",
            "sensor_failure_detected",
            "abnormal_consumption_detected",
            "battery_error_code",
            "device_error_code",
        ],
    },
    "location": {
        "required": [
            "message_id",
            "schema_version",
            "message_type",
            "device_id",
            "kit_id",
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

    return {"valid": not errors, "errors": errors}


def validate_prediction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate records that will be sent to maintenance/security models.

    Other message types can be useful for ingestion, but the current local
    models require a complete telemetry record.
    """

    validation = validate_payload(payload)
    errors = list(validation.get("errors", []))
    if payload.get("message_type") != "telemetry":
        errors.append("message_type must be telemetry for maintenance/security prediction")
    return {"valid": bool(validation["valid"]) and not errors, "errors": errors}
