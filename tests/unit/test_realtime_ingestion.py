from djua_energy.database.realtime_store import RealtimeTelemetryStore
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService
from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator


def test_realtime_ingestion_persists_state_history_and_ignores_duplicates(tmp_path) -> None:
    store = RealtimeTelemetryStore(tmp_path / "realtime.sqlite")
    service = TelemetryIngestionService(
        LocalInferenceEngine("artifacts"),
        realtime_store=store,
        sliding_window_size=6,
    )
    records = SyntheticTelemetryGenerator(seed=123, num_kits=1).generate(
        scenarios=["normal_operation"],
        duration_hours=2,
    )[:4]

    for record in records:
        result = service.process_window([record])
        assert result["status"] == "processed"
        assert result["prediction_window_records"] >= 1
        assert result["stored_prediction"]["device_id"] == "device-0"

    duplicate = service.process_window([records[-1]])

    assert duplicate["status"] == "no_new_records"
    assert duplicate["duplicate_records"] == 1

    state = store.get_device_state("device-0")
    history = store.prediction_history("device-0")

    assert state is not None
    assert state["device_id"] == "device-0"
    assert state["risk_score"] >= 0
    assert len(history) == 4
    assert history[0]["records_used"] <= 6
