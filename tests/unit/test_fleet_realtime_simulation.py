from scripts.simulate_fleet_realtime import build_records
from djua_energy.database.realtime_store import RealtimeTelemetryStore
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService
from djua_energy.pipeline.contracts import validate_payload
from djua_energy.pipeline.inference import LocalInferenceEngine


def test_fleet_realtime_simulation_generates_valid_progressive_payloads() -> None:
    records = build_records(
        cycles=4,
        interval_seconds=300,
        devices=3,
        seed=1234,
        start_time=1_800_000_000,
        run_id="test",
    )

    assert len(records) == 12
    for record in records:
        assert validate_payload(record)["valid"]
        assert record["latitude"] is not None
        assert record["longitude"] is not None
        assert record["ambient_temperature_c"] is not None
        assert record["battery_age_months"] >= 3

    device_001 = [record for record in records if record["device_id"] == "device-001"]
    assert [record["sequence_number"] for record in device_001] == [1, 2, 3, 4]
    assert [int(record["event_time"]) for record in device_001] == [
        1_800_000_000,
        1_800_000_300,
        1_800_000_600,
        1_800_000_900,
    ]
    assert device_001[-1]["battery_age_months"] > device_001[0]["battery_age_months"]


def test_fleet_realtime_records_update_each_device_state(tmp_path) -> None:
    records = build_records(
        cycles=3,
        interval_seconds=300,
        devices=2,
        seed=5678,
        start_time=1_800_000_000,
        run_id="service-test",
    )
    store = RealtimeTelemetryStore(tmp_path / "fleet.sqlite")
    service = TelemetryIngestionService(
        LocalInferenceEngine("artifacts"),
        realtime_store=store,
        sliding_window_size=6,
    )

    for record in records:
        result = service.process_window([record])
        assert result["status"] == "processed"
        assert result["stored_prediction"]["device_id"] == record["device_id"]

    fleet_state = store.list_device_states()
    assert len(fleet_state) == 2
    assert store.get_device_state("device-001") is not None
    assert store.get_device_state("device-002") is not None
    assert len(store.prediction_history("device-001")) == 3
    assert len(store.prediction_history("device-002")) == 3
