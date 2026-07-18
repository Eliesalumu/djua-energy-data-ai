import json
from pathlib import Path

import apps.api.main as api_main
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator


def _reset_telemetry_service() -> None:
    api_main.telemetry_service = TelemetryIngestionService(api_main.engine)


def test_telemetry_analyze_endpoint_processes_records() -> None:
    _reset_telemetry_service()
    records = SyntheticTelemetryGenerator(seed=101, num_kits=1).generate(
        scenarios=["movement_then_connectivity_loss"],
        duration_hours=1,
    )

    body = api_main.telemetry_analyze(api_main.TelemetryWindowRequest(records=records))

    assert body["status"] == "processed"
    assert body["records_analyzed"] == len(records)
    assert body["alert"]["priority"] in {"none", "medium", "high", "critical"}


def test_telemetry_analyze_endpoint_quarantines_invalid_records() -> None:
    _reset_telemetry_service()
    invalid_record = {
        "message_id": "bad-1",
        "schema_version": "1.0",
        "message_type": "telemetry",
    }

    body = api_main.telemetry_analyze(api_main.TelemetryWindowRequest(records=[invalid_record]))

    assert body["status"] == "no_new_records"
    assert body["quarantined_records"] == 1

    quarantine = api_main.telemetry_quarantine()
    assert len(quarantine["entries"]) == 1


def test_observability_endpoints_expose_metrics_and_audit() -> None:
    _reset_telemetry_service()
    records = SyntheticTelemetryGenerator(seed=202, num_kits=1).generate(
        scenarios=["normal_operation"],
        duration_hours=1,
    )

    api_main.telemetry_analyze(api_main.TelemetryWindowRequest(records=records))

    metrics = api_main.telemetry_metrics()
    audit = api_main.telemetry_audit()

    assert metrics["predictions.completed"] == 1
    assert audit["events"]


def test_telemetry_schema_matches_current_required_contract() -> None:
    schema = json.loads(Path("schemas/telemetry.v1.schema.json").read_text(encoding="utf-8"))

    for field in [
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
    ]:
        assert field in schema["required"]
        assert field in schema["properties"]

    for field in [
        "solar_power_w",
        "load_power_w",
        "movement_detected",
        "tamper_detected",
        "enclosure_opened",
        "connectivity_gap_seconds",
        "device_temperature_c",
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
    ]:
        assert field in schema["properties"]
