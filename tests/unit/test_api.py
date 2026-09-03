import json
from pathlib import Path

import apps.api.main as api_main
from djua_energy.database.realtime_store import RealtimeTelemetryStore
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator


def _reset_telemetry_service() -> None:
    api_main.telemetry_service = TelemetryIngestionService(api_main.engine)


def _paid_payment(payment_id: str, paid_at: str = "2026-08-10T10:00:00+02:00") -> dict:
    return {
        "payment_id": payment_id,
        "contract_id": "contract-001",
        "client_id": "client-001",
        "due_date": "2026-08-10T00:00:00+02:00",
        "paid_at": paid_at,
        "days_late": 0,
        "amount_due": 20,
        "amount_paid": 20,
        "status": "paid",
        "method": "orange_money",
    }


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


def test_customer_decision_from_telemetry_builds_kit_intelligence(tmp_path, monkeypatch) -> None:
    store = RealtimeTelemetryStore(tmp_path / "customer.sqlite")
    monkeypatch.setattr(api_main, "realtime_store", store)
    records = SyntheticTelemetryGenerator(seed=303, num_kits=1).generate(
        scenarios=["overheating"],
        duration_hours=1,
    )[:4]
    latest = records[-1]
    payload = api_main.CustomerDecisionFromTelemetryRequest(
        schema_version="1.0",
        request_id="req-from-telemetry",
        as_of="2026-08-20T10:00:00+02:00",
        identity={
            "client_id": "client-001",
            "kit_id": latest["kit_id"],
            "device_id": latest["device_id"],
            "contract_id": "contract-001",
            "assignment_id": "assignment-001",
            "resolution_status": "resolved",
        },
        records=records,
        payments=[_paid_payment("pay-001"), _paid_payment("pay-002", "2026-07-12T10:00:00+02:00")],
        customer={"tenure_months": 18, "active_contracts": 1, "customer_segment": "residential"},
        contract={"periodic_amount_usd": 20, "status": "active"},
        data_quality={"identity_resolved": True, "missing_features": [], "warnings": []},
    )

    body = api_main.customer_decision_evaluate_from_telemetry(payload)

    assert body["request_id"] == "req-from-telemetry"
    assert body["identity"]["client_id"] == "client-001"
    assert body["scores"]["operational_risk"] >= 0
    assert body["identity_contract"]["status"] == "resolved"
    assert body["kit_intelligence_source"]["kind"] == "model_output"
    assert body["kit_intelligence_source"]["kit_intelligence"]["operational_risk"]["score"] >= 0
    assert body["kit_intelligence_source"]["maintenance_prediction"]["technical_risk_probability"] >= 0
    assert body["trend_source"]["new_records"] == len(records)
    assert body["trend_source"]["prediction_window_records"] == len(records)
    assert body["persistence"]["stored"] is True

    history = api_main.customer_decision_history(client_id="client-001")
    assert len(history["items"]) == 1
    detail = api_main.customer_decision_detail(body["persistence"]["decision_id"])
    assert detail["result"]["request_id"] == "req-from-telemetry"
    assert detail["input_snapshot"]["payment"]["source"] == "computed_from_raw_payments"
    assert detail["input_snapshot"]["payment"]["payments_last_6_months"] == 2
    assert len(detail["input_snapshot"]["raw_payments"]) == 2
    customer = api_main.customer_profile_detail("client-001")
    assert customer["latest_kit_id"] == latest["kit_id"]
    assert customer["latest_device_id"] == latest["device_id"]
    assert customer["latest_decision_id"] == body["persistence"]["decision_id"]
    assert customer["latest_operational_risk_score"] == body["scores"]["operational_risk"]

    stored_records = store.recent_records_for_device(latest["device_id"], limit=10)
    assert stored_records[-1]["client_id"] == "client-001"
    stored_predictions = store.prediction_history(latest["device_id"])
    assert stored_predictions[0]["client_id"] == "client-001"
    api_predictions = api_main.prediction_history_v1(client_id="client-001")
    assert api_predictions["items"][0]["kit_id"] == latest["kit_id"]
    state = store.get_device_state(latest["device_id"])
    assert state["client_id"] == "client-001"


def test_customer_decision_from_telemetry_uses_backend_resolved_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(api_main, "realtime_store", RealtimeTelemetryStore(tmp_path / "customer.sqlite"))
    records = SyntheticTelemetryGenerator(seed=404, num_kits=1).generate(
        scenarios=["normal_operation"],
        duration_hours=1,
    )[:3]
    latest = records[-1]

    payload = api_main.CustomerDecisionFromTelemetryRequest(
        schema_version="1.0",
        request_id="req-history",
        as_of="2026-08-20T10:00:00+02:00",
        identity={
            "assignment_id": "assignment-history-001",
            "client_id": "client-history-001",
            "kit_id": latest["kit_id"],
            "device_id": latest["device_id"],
            "contract_id": "contract-history-001",
            "resolution_status": "resolved",
        },
        records=records,
        payments=[_paid_payment("pay-history-001")],
        customer={"tenure_months": 12, "active_contracts": 1, "customer_segment": "residential"},
        contract={"periodic_amount_usd": 20, "status": "active"},
        data_quality={"missing_features": [], "warnings": []},
    )

    body = api_main.customer_decision_evaluate_from_telemetry(payload)

    assert body["identity_contract"]["status"] == "resolved"
    assert body["identity"]["client_id"] == "client-history-001"
    assert body["identity"]["assignment_id"] == "assignment-history-001"


def test_customer_decision_from_telemetry_blocks_unresolved_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(api_main, "realtime_store", RealtimeTelemetryStore(tmp_path / "customer.sqlite"))
    records = SyntheticTelemetryGenerator(seed=505, num_kits=1).generate(
        scenarios=["normal_operation"],
        duration_hours=1,
    )[:3]
    latest = records[-1]
    payload = api_main.CustomerDecisionFromTelemetryRequest(
        schema_version="1.0",
        request_id="req-unresolved",
        as_of="2026-08-20T10:00:00+02:00",
        identity={
            "kit_id": latest["kit_id"],
            "device_id": latest["device_id"],
            "resolution_status": "unresolved",
        },
        records=records,
        payments=[_paid_payment("pay-unresolved-001")],
        customer={"tenure_months": 12, "active_contracts": 1, "customer_segment": "residential"},
        contract={"periodic_amount_usd": 20, "status": "active"},
        data_quality={"missing_features": [], "warnings": []},
    )

    body = api_main.customer_decision_evaluate_from_telemetry(payload)

    assert body["identity_contract"]["status"] == "unresolved"
    assert body["identity_status"] == "unresolved"
    assert body["decision"]["recommended_action"] == "resolve_identity"
    assert body["confidence"] == 0


def test_backend_resolved_events_sync_consumes_backend_snapshots(tmp_path, monkeypatch) -> None:
    store = RealtimeTelemetryStore(tmp_path / "backend-sync.sqlite")
    monkeypatch.setattr(api_main, "realtime_store", store)
    records = SyntheticTelemetryGenerator(seed=606, num_kits=1).generate(
        scenarios=["normal_operation"],
        duration_hours=1,
    )[:3]
    latest = records[-1]
    snapshot = {
        "schema_version": "1.0",
        "request_id": "req-backend-pull-001",
        "as_of": "2026-08-20T10:00:00+02:00",
        "identity": {
            "client_id": "client-pull-001",
            "kit_id": latest["kit_id"],
            "device_id": latest["device_id"],
            "contract_id": "contract-pull-001",
            "assignment_id": "assignment-pull-001",
            "resolution_status": "resolved",
        },
        "records": records,
        "payments": [_paid_payment("pay-pull-001")],
        "customer": {"tenure_months": 14, "active_contracts": 1, "customer_segment": "residential"},
        "contract": {"periodic_amount_usd": 20, "status": "active"},
        "data_quality": {"identity_resolved": True, "missing_features": [], "warnings": []},
    }

    class FakeBackendResolvedEventsClient:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def process_resolved_events(self, *, processor, cursor, limit, ack) -> dict:
            result = processor(snapshot)
            ack_payload = {
                "status": "processed",
            }
            return {
                "status": "completed",
                "received": 1,
                "processed_count": 1,
                "failed_count": 0,
                "next_cursor": None,
                "processed": [
                    {
                        "request_id": snapshot["request_id"],
                        "ack_sent": ack,
                        "ack_payload": ack_payload,
                        "decision_id": result["persistence"]["decision_id"],
                        "prediction_id": result["trend_source"]["stored_prediction_id"],
                    }
                ],
                "failed": [],
            }

    monkeypatch.setattr(api_main, "BackendResolvedEventsClient", FakeBackendResolvedEventsClient)

    body = api_main.backend_resolved_events_sync(
        api_main.BackendResolvedEventsSyncRequest(
            backend_base_url="http://backend.test",
            limit=25,
            ack=True,
        )
    )

    assert body["status"] == "completed"
    assert body["processed_count"] == 1
    assert body["processed"][0]["request_id"] == "req-backend-pull-001"
    assert body["processed"][0]["ack_payload"] == {"status": "processed"}
    assert body["processed"][0]["decision_id"]
    assert body["processed"][0]["prediction_id"]
    assert api_main.customer_profile_detail("client-pull-001")["latest_kit_id"] == latest["kit_id"]
    dashboard = api_main.frontend_live_ui()
    assert dashboard["meta"]["schema_version"] == "frontend-live.v1"
    assert dashboard["customer_profile"]["customers"][0]["client_id"] == "client-pull-001"
    assert dashboard["customer_profile"]["recent_decisions"][0]["request_id"] == "req-backend-pull-001"
    assert "customers" in dashboard["administration"]["data_tables"]


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
            "identity": {"client_id": "client-jury-001", "kit_id": "kit-jury-001"},
            "payments": [
                {"status": "paid", "amount_due": 20, "amount_paid": 20},
                {"status": "late", "amount_due": 20, "amount_paid": 20},
                {"status": "missed", "amount_due": 20, "amount_paid": 0},
                {"status": "failed", "amount_due": 20, "amount_paid": 0},
            ],
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
                "client_value": 55,
                "payment_risk": 100,
                "operational_risk": 82,
                "intervention_priority": 91,
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
    assert "paiement" not in body["answer"].lower()
    assert "payments[]" not in body["answer"]

    payment_body = api_main.demo_kit_console_chat(
        api_main.KitConsoleChatRequest(
            message="Qu'est-ce qui justifie le risque de paiement de 100% ?",
            context=console_context,
        )
    )
    assert "payments[]" in payment_body["answer"]
    assert "retard" in payment_body["answer"]
    assert "impaye" in payment_body["answer"]
    assert "batterie" not in payment_body["answer"].lower()


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
