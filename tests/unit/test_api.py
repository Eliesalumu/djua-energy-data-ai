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
    assert decision["client_id"] == "client-001"
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


def test_frontend_digital_twin_and_customer_profile_are_coherent() -> None:
    twin = api_main.frontend_kit_digital_twin("kit-0")
    customer = api_main.frontend_customer_risk_profile("client-001")

    assert twin["identity"]["kit_id"] == "kit-0"
    assert twin["identity"]["client_id"] == "client-001"
    assert twin["battery"]["voltage"]["unit"] == "V"
    assert twin["health"]["source"]["kind"] == "model_derived"
    assert twin["maintenance_prediction"]["source"]["kind"] == "model_output"
    assert twin["telemetry"]["series"]
    assert customer["customer"]["client_id"] == "client-001"
    assert customer["customer"]["source"]["kind"] == "model_derived"
    assert customer["payment_risk"]["source"]["kind"] == "not_available"
    assert customer["recommendations"]


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


def test_frontend_business_schemas_are_actionable() -> None:
    intervention_schema = json.loads(Path("schemas/intervention.v1.schema.json").read_text(encoding="utf-8"))
    customer_schema = json.loads(Path("schemas/customer.v1.schema.json").read_text(encoding="utf-8"))

    for field in ["intervention_id", "decision_id", "kit_id", "type", "priority", "status", "reason"]:
        assert field in intervention_schema["required"]
        assert field in intervention_schema["properties"]

    for field in ["client_id", "name", "risk_score", "risk_level", "source"]:
        assert field in customer_schema["required"]
        assert field in customer_schema["properties"]

    assert "payment_risk" in customer_schema["properties"]
    assert "estimated_cost" in intervention_schema["properties"]
