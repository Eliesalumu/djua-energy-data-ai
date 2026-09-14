import json
from pathlib import Path

import apps.api.main as api_main
from djua_energy.database.realtime_store import RealtimeTelemetryStore
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

    body = api_main.telemetry_analyze(api_main.TelemetryIngestionRequest(records=records))

    assert body["status"] == "processed"
    assert body["records_analyzed"] == len(records)
    assert body["alert"]["priority"] in {"none", "medium", "high", "critical"}


def test_ai_chat_endpoint_returns_conversational_payload(monkeypatch) -> None:
    class FakeResult:
        def to_dict(self) -> dict:
            return {
                "answer": "Le device-3 est dans un etat critique.",
                "intent": "device_diagnosis",
                "device_id": "device-3",
                "used_llm": False,
                "sources": ["data/generated/mvp_dataset.csv"],
                "context": {"device_id": "device-3"},
                "error": None,
            }

    class FakeChatService:
        def answer(self, message: str) -> FakeResult:
            assert message == "Parle-moi du device-3"
            return FakeResult()

    monkeypatch.setattr(api_main, "chat_service", FakeChatService())

    body = api_main.ai_chat(api_main.AiChatRequest(message="Parle-moi du device-3"))

    assert body["device_id"] == "device-3"
    assert body["answer"]
    assert body["sources"]


def test_telemetry_analyze_endpoint_quarantines_invalid_records() -> None:
    _reset_telemetry_service()
    invalid_record = {
        "message_id": "bad-1",
        "schema_version": "1.0",
        "message_type": "telemetry",
    }

    body = api_main.telemetry_analyze(api_main.TelemetryIngestionRequest(records=[invalid_record]))

    assert body["status"] == "no_new_records"
    assert body["quarantined_records"] == 1

    quarantine = api_main.telemetry_quarantine()
    assert len(quarantine["entries"]) == 1


def test_telemetry_analyze_quarantines_non_prediction_message_types() -> None:
    _reset_telemetry_service()
    location_record = {
        "message_id": "loc-1",
        "schema_version": "1.0",
        "message_type": "location",
        "device_id": "device-1",
        "kit_id": "kit-1",
        "serial_number": "SN-1",
        "event_time": "1700000000",
        "sequence_number": 1,
        "latitude": 1.0,
        "longitude": 2.0,
        "gps_accuracy_m": 5,
    }

    body = api_main.telemetry_analyze(api_main.TelemetryIngestionRequest(records=[location_record]))

    assert body["status"] == "no_new_records"
    assert body["quarantined_records"] == 1
    assert "message_type must be telemetry" in api_main.telemetry_quarantine()["entries"][0]["errors"][0]


def test_observability_endpoints_expose_metrics_and_audit() -> None:
    _reset_telemetry_service()
    records = SyntheticTelemetryGenerator(seed=202, num_kits=1).generate(
        scenarios=["normal_operation"],
        duration_hours=1,
    )

    api_main.telemetry_analyze(api_main.TelemetryIngestionRequest(records=records))

    metrics = api_main.telemetry_metrics()
    audit = api_main.telemetry_audit()

    assert metrics["predictions.completed"] == 1
    assert audit["events"]


def test_frontend_command_center_exposes_display_ready_payload() -> None:
    body = api_main.frontend_command_center()

    assert body["meta"]["schema_version"] == "frontend.v1"
    assert body["summary"]
    assert body["priority_alerts"]
    assert body["fleet_map"]["points"]
    assert body["decision_engine"]["by_severity"]["critical"] >= 1
    assert body["system_status"]
    assert body["recent_activity"]
    assert "model_runs" in body["meta"]
    assert "LocalInferenceEngine" in body["meta"]["ai_traceability"]

    metric = body["summary"][0]
    for field in ["id", "label", "value", "unit", "period", "last_updated_at", "freshness"]:
        assert field in metric


def test_frontend_decision_detail_keeps_entity_links() -> None:
    body = api_main.frontend_decision_detail("decision-001")

    decision = body["decision"]
    assert decision["decision_id"] == "decision-001"
    assert decision["kit_id"] == "kit-0"
    assert decision["source"]["kind"] == "model_output"
    assert decision["model_outputs"]["maintenance"]["model_version"]
    assert decision["model_outputs"]["security"]["model_version"]
    assert body["risk_factors"]
    assert body["evidence"]
    assert body["timeline"]
    assert body["feedback_options"]
    assert body["score_history"]["series"][-1]["source"]["kind"] == "model_output"


def test_frontend_create_intervention_exposes_workflow_payload() -> None:
    body = api_main.frontend_create_intervention("decision-001")

    assert body["meta"]["schema_version"] == "create-intervention.v1"
    assert body["context"]["decision"]["decision_id"] == "decision-001"
    assert body["context"]["kit"]["kit_id"] == body["draft"]["kit_id"]
    assert body["draft"]["status"] == "draft"
    assert body["draft"]["source"]["kind"] == "model_derived"
    assert body["form_options"]["technicians"]
    assert body["form_options"]["time_slots"]
    assert body["validation_rules"]
    assert body["actions"][0]["id"] == "save_draft"
    assert body["actions"][1]["source"]["kind"] == "not_available"



def test_frontend_supporting_endpoints_expose_admin_performance_and_realtime() -> None:
    fleet = api_main.frontend_fleet()
    performance = api_main.frontend_performance()
    admin = api_main.frontend_admin_data_ai()
    realtime = api_main.frontend_realtime_events()

    assert fleet["pagination"]["total"] == len(fleet["kits"])
    assert performance["models"]
    assert performance["models"][0]["source"]["kind"] == "artifact_metadata"
    assert performance["financial_impact"]["methodology"]
    assert performance["financial_impact"]["source"]["kind"] == "not_available"
    assert admin["models"]
    assert admin["data_quality"]["message"]
    assert realtime["subscriptions"]
    assert realtime["events"][0]["correlation_id"]
    assert realtime["events"][0]["source"]["kind"] == "model_derived"


def test_telemetry_schema_matches_current_required_contract() -> None:
    schema = json.loads(Path("schemas/telemetry.v1.schema.json").read_text(encoding="utf-8"))

    for field in [
        "message_id",
        "schema_version",
        "message_type",
        "device_id",
        "kit_id",
        "battery_voltage_v",
        "battery_current_a",
        "battery_power_w",
        "battery_temperature_c",
        "state_of_charge_pct",
        "state_of_health_pct",
    ]:
        assert field in schema["required"]
    for field in ["serial_number", "event_time", "sequence_number"]:
        assert field not in schema["required"]
        assert field not in schema["properties"]

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






def test_device_evaluate_from_telemetry_builds_kit_intelligence(tmp_path, monkeypatch) -> None:
    store = RealtimeTelemetryStore(tmp_path / "device.sqlite")
    monkeypatch.setattr(api_main, "realtime_store", store)
    records = SyntheticTelemetryGenerator(seed=303, num_kits=1).generate(
        scenarios=["overheating"],
        duration_hours=1,
    )[:4]
    records = [
        {key: value for key, value in record.items() if key not in {"serial_number", "event_time", "sequence_number"}}
        for record in records
    ]
    latest = records[-1]
    payload = api_main.DeviceTelemetryEvaluationRequest(
        schema_version="1.0",
        request_id="req-device",
        as_of="2026-08-20T10:00:00+02:00",
        device_id=latest["device_id"],
        kit_id=latest["kit_id"],
        records=records,
        data_quality={"missing_features": [], "warnings": []},
    )

    body = api_main.device_evaluate_from_telemetry(payload)

    assert body["request_id"] == "req-device"
    assert body["device_id"] == latest["device_id"]
    assert body["kit_id"] == latest["kit_id"]
    assert body["maintenance_prediction"]["technical_risk_probability"] >= 0
    assert body["security_prediction"]["suspicious_activity_score"] >= 0
    assert body["kit_intelligence"]["operational_risk"]["score"] >= 0
    assert body["trend_source"]["new_records"] == len(records)
    assert body["trend_source"]["prediction_window_records"] == len(records)

    stored_records = store.recent_records_for_device(latest["device_id"], limit=10)
    assert stored_records[-1]["device_id"] == latest["device_id"]
    stored_predictions = store.prediction_history(latest["device_id"])
    assert stored_predictions[0]["kit_id"] == latest["kit_id"]
    assert store.get_device_state(latest["device_id"])["kit_id"] == latest["kit_id"]

def test_demo_kit_console_page_and_context_chat(monkeypatch) -> None:
    class FakeLlmClient:
        available = False

    class FakeChatService:
        llm_client = FakeLlmClient()

    monkeypatch.setattr(api_main, "chat_service", FakeChatService())

    page = api_main.demo_kit_console()
    assert str(page.path).endswith("kit_console.html")

    console_context = {
        "payload": {
            "device_id": "device-jury-001",
            "kit_id": "kit-jury-001",
            "records": [
                {
                    "battery_temperature_c": 55,
                    "battery_voltage_v": 11.7,
                    "state_of_health_pct": 62,
                    "connectivity_gap_seconds": 420,
                    "geofence_status": "inside",
                    "movement_detected": False,
                    "enclosure_opened": False,
                    "tamper_detected": False,
                    "abnormal_consumption_detected": True,
                }
            ],
        },
        "prediction": {
            "scores": {
                "operational_risk": 82,
            },
            "decision": {"priority": "high", "recommended_action": "technical_intervention"},
            "kit_intelligence_source": {
                "maintenance_prediction": {
                    "technical_risk_probability": 0.87,
                    "suspected_component": "battery",
                },
                "security_prediction": {
                    "suspicious_activity_score": 0.12,
                    "suspected_event_types": [],
                },
            },
        },
    }

    body = api_main.demo_kit_console_chat(
        api_main.KitConsoleChatRequest(
            message="Pourquoi ce kit est critique ?",
            context=console_context,
        )
    )

    assert body["used_llm"] is False
    assert "local_fallback" in body["sources"]
    assert "kit-jury-001" in body["answer"]
    assert "temperature batterie" in body["answer"]


def test_demo_kit_console_chat_uses_llm_for_technical_questions_when_available(monkeypatch) -> None:
    class FakeLlmClient:
        available = True

        def generate(self, message: str, context: dict) -> str:
            assert "Pourquoi ce kit est critique" in message
            assert context["requested_domain"] == "maintenance"
            return "Reponse OpenAI contextualisee."

    class FakeChatService:
        llm_client = FakeLlmClient()

    monkeypatch.setattr(api_main, "chat_service", FakeChatService())

    body = api_main.demo_kit_console_chat(
        api_main.KitConsoleChatRequest(
            message="Pourquoi ce kit est critique cote maintenance ?",
            context={
                "payload": {
                    "identity": {"kit_id": "kit-jury-001"},
                    "records": [{"battery_temperature_c": 55}],
                },
                "prediction": {
                    "scores": {"operational_risk": 82},
                    "decision": {"priority": "high", "recommended_action": "technical_intervention"},
                },
            },
        )
    )

    assert body["used_llm"] is True
    assert body["answer"] == "Reponse OpenAI contextualisee."
    assert "OpenAIResponsesClient" in body["sources"]


def test_demo_kit_console_chat_falls_back_when_llm_crashes(monkeypatch) -> None:
    class BrokenLlmClient:
        available = True

        def generate(self, message: str, context: dict) -> str:
            raise AttributeError("model configuration missing")

    class FakeChatService:
        llm_client = BrokenLlmClient()

    monkeypatch.setattr(api_main, "chat_service", FakeChatService())

    body = api_main.demo_kit_console_chat(
        api_main.KitConsoleChatRequest(
            message="Que doit faire le technicien maintenant ?",
            context={
                "payload": {
                    "device_id": "device-jury-001",
                    "kit_id": "kit-jury-001",
                    "records": [
                        {
                            "battery_temperature_c": 55,
                            "battery_voltage_v": 11.7,
                            "state_of_health_pct": 62,
                            "abnormal_consumption_detected": True,
                        }
                    ],
                },
                "prediction": {
                    "scores": {"operational_risk": 82},
                    "decision": {"priority": "high", "recommended_action": "technical_intervention"},
                },
            },
        )
    )

    assert body["used_llm"] is False
    assert body["error"] == "model configuration missing"
    assert "local_fallback" in body["sources"]

