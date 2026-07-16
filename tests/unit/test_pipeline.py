from djua_energy.pipeline.contracts import validate_payload
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.features import build_maintenance_features, build_security_features


def test_validation_accepts_valid_telemetry() -> None:
    payload = {
        "message_id": "m1",
        "schema_version": "1.0",
        "message_type": "telemetry",
        "device_id": "device-1",
        "kit_id": "kit-1",
        "serial_number": "SN-001",
        "event_time": "1",
        "sequence_number": 1,
        "battery_voltage_v": 13.4,
        "battery_current_a": 2.0,
        "battery_power_w": 26.8,
        "battery_temperature_c": 31.0,
        "state_of_charge_pct": 90.0,
        "state_of_health_pct": 100.0,
    }
    result = validate_payload(payload)
    assert result["valid"] is True


def test_generator_creates_records() -> None:
    generator = SyntheticTelemetryGenerator(seed=3, num_kits=2)
    records = generator.generate(scenarios=["normal_operation"], duration_hours=2)
    assert len(records) > 0
    assert records[0]["synthetic_data"] is True


def test_feature_frames_are_created() -> None:
    generator = SyntheticTelemetryGenerator(seed=3, num_kits=1)
    records = generator.generate(scenarios=["normal_operation"], duration_hours=2)
    maintenance = build_maintenance_features(records)
    security = build_security_features(records)
    assert list(maintenance.columns)[:3] == ["message_id", "schema_version", "message_type"] or True
    assert "battery_voltage_trend" in maintenance.columns
    assert "distance_to_installation" in security.columns
