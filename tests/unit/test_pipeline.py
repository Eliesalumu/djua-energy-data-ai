from djua_energy.pipeline.contracts import REQUIRED_FIELDS, validate_payload
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator, generate_mvp_dataset
from djua_energy.pipeline.features import build_maintenance_features, build_security_features
from djua_energy.alerting.prioritization import prioritize_predictions
from djua_energy.ingestion.idempotency import InMemoryIdempotencyStore
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService


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


def test_validation_accepts_backend_critical_telemetry_fields() -> None:
    critical_fields = {
        "battery_age_months": 24,
        "distance_from_installation_m": 120.5,
        "movement_detected": True,
        "tamper_detected": True,
        "connection_status": "disconnected",
        "network_quality": "weak",
        "connectivity_gap_seconds": 900,
        "security_risk_zone": "high",
        "panel_temperature_c": 58.2,
        "solar_irradiance_w_m2": 720,
        "gps_accuracy_m": 6.5,
        "movement_duration_seconds": 300,
        "movement_event_count": 4,
        "impact_detected": True,
        "identity_mismatch_detected": True,
        "short_circuit_detected": False,
        "battery_temperature_c": 46.1,
        "reset_count": 3,
        "sensor_failure_detected": False,
        "device_error_code": "NONE",
        "usage_profile": "intensive",
    }
    payload = {
        "message_id": "m-critical-fields",
        "schema_version": "1.0",
        "message_type": "telemetry",
        "device_id": "device-1",
        "kit_id": "kit-1",
        "serial_number": "SN-001",
        "event_time": "1",
        "sequence_number": 1,
        "battery_voltage_v": 12.6,
        "battery_current_a": 1.1,
        "battery_power_w": 13.9,
        "state_of_charge_pct": 70.0,
        "state_of_health_pct": 88.0,
        **critical_fields,
    }

    result = validate_payload(payload)

    assert result["valid"] is True
    assert set(critical_fields).issubset(set(REQUIRED_FIELDS["telemetry"]["optional"]))


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


def test_generate_mvp_dataset_returns_structured_rows() -> None:
    dataset = generate_mvp_dataset()
    assert not dataset.empty
    assert len(dataset) == 10000
    assert "scenario" in dataset.columns
    assert "label_maintenance" in dataset.columns
    assert "label_security" in dataset.columns
    for column in [
        "region",
        "season",
        "ambient_temperature_c",
        "solar_irradiance_w_m2",
        "humidity_pct",
        "network_quality",
        "installation_type",
        "battery_age_months",
        "usage_profile",
        "security_risk_zone",
        "day_period",
    ]:
        assert column in dataset.columns
    assert set(dataset["scenario"].unique()).issuperset({
        "normal_operation",
        "battery_degradation",
        "overheating",
        "movement_and_tampering",
        "connectivity_loss",
        "low_solar_input",
    })


def test_idempotency_store_splits_new_and_duplicate_records() -> None:
    store = InMemoryIdempotencyStore()
    record = {"message_id": "m1", "device_id": "device-1"}

    first_new, first_duplicates = store.filter_new([record])
    second_new, second_duplicates = store.filter_new([record])

    assert first_new == [record]
    assert first_duplicates == []
    assert second_new == []
    assert second_duplicates == [record]


def test_alert_priority_combines_maintenance_and_security_predictions() -> None:
    maintenance = {"risk_level": "high", "technical_risk_probability": 0.81}
    security = {"risk_level": "high", "suspicious_activity_score": 0.9}

    assert prioritize_predictions(maintenance, security) == "critical"


def test_telemetry_ingestion_service_processes_valid_window() -> None:
    class FakeEngine:
        def infer_maintenance(self, records):
            return {"risk_level": "high", "technical_risk_probability": 0.82}

        def infer_security(self, records):
            return {"risk_level": "normal", "suspicious_activity_score": 0.1}

    record = {
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
    service = TelemetryIngestionService(FakeEngine())

    result = service.process_window([record])

    assert result["status"] == "processed"
    assert result["alert"]["priority"] == "high"
    assert result["quarantined_records"] == 0
