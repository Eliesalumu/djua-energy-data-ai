from __future__ import annotations

import json
from pathlib import Path

import apps.api.main as api_main
from djua_energy.database.realtime_store import RealtimeTelemetryStore
from djua_energy.scoring.decision_engine import CustomerDecisionEngine


def _base_context() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "req-test-001",
        "as_of": "2026-08-18T14:30:00+02:00",
        "identity": {
            "client_id": "client-001",
            "kit_id": "kit-001",
            "device_id": "device-001",
            "installation_id": "installation-001",
            "contract_id": "contract-001",
            "assignment_id": "assignment-001",
            "resolution_status": "resolved",
        },
        "telemetry": {
            "event_time": "2026-08-18T14:29:45+02:00",
            "battery_temperature_c": 36,
            "state_of_charge_pct": 72,
            "state_of_health_pct": 92,
            "connection_status": "connected",
        },
        "context": {
            "region": "kinshasa",
            "season": "dry",
            "day_period": "afternoon",
            "ambient_temperature_c": 33,
        },
        "payment": {
            "payments_last_6_months": 6,
            "late_payments_last_6_months": 0,
            "missed_payments_last_6_months": 0,
            "failed_payments_last_6_months": 0,
            "payment_success_rate": 1.0,
            "average_days_late": 0,
            "outstanding_balance": 0,
            "days_since_last_payment": 8,
            "last_payment_status": "paid",
        },
        "customer": {
            "tenure_months": 18,
            "active_contracts": 1,
            "customer_segment": "residential",
        },
        "contract": {
            "periodic_amount_usd": 20,
            "status": "active",
        },
        "kit_intelligence": {
            "maintenance_risk": 0.18,
            "security_risk": 0.08,
            "battery_health": "healthy",
            "critical_anomaly": False,
        },
        "data_quality": {
            "identity_resolved": True,
            "telemetry_age_seconds": 15,
            "missing_features": [],
        },
    }


def test_customer_decision_valid_client_and_kit_returns_dimension_scores() -> None:
    result = CustomerDecisionEngine().evaluate(_base_context())

    assert result["identity_status"] == "resolved"
    assert result["data_quality"]["status"] == "complete"
    assert set(result["scores"]) == {
        "client_value",
        "payment_risk",
        "operational_risk",
        "intervention_priority",
    }
    assert result["decision"]["recommended_action"] == "monitor"
    assert result["scores"]["payment_risk"] == 10
    assert result["confidence"] >= 0.8


def test_customer_decision_supports_client_with_multiple_kits_as_value_signal() -> None:
    payload = _base_context()
    payload["customer"]["active_contracts"] = 3

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["client_value"] > CustomerDecisionEngine().evaluate(_base_context())["scores"]["client_value"]
    assert result["identity_status"] == "resolved"


def test_customer_decision_blocks_kit_without_customer() -> None:
    payload = _base_context()
    payload["identity"]["client_id"] = None

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["identity_status"] == "kit_without_customer"
    assert result["decision"]["recommended_action"] == "resolve_identity"
    assert result["confidence"] == 0
    assert "identity.client_id" in result["data_quality"]["missing_features"]


def test_customer_decision_handles_missing_payment_data_explicitly() -> None:
    payload = _base_context()
    payload["payment"] = {}

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["payment_risk"] == 50
    assert result["data_quality"]["status"] == "partial"
    assert "payment" in result["data_quality"]["missing_features"]


def test_customer_decision_marks_stale_telemetry_as_partial_quality() -> None:
    payload = _base_context()
    payload["data_quality"]["telemetry_age_seconds"] = 7200

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["data_quality"]["status"] == "partial"
    assert result["data_quality"]["telemetry_age_seconds"] == 7200
    assert any("obsolete" in warning for warning in result["data_quality"]["warnings"])


def test_customer_decision_detects_critical_technical_anomaly() -> None:
    payload = _base_context()
    payload["kit_intelligence"]["maintenance_risk"] = 0.92
    payload["kit_intelligence"]["critical_anomaly"] = True
    payload["telemetry"]["battery_temperature_c"] = 51

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["operational_risk"] >= 90
    assert result["decision"]["recommended_action"] == "urgent_technical_intervention"
    assert "critical_anomaly" in result["reasons"]


def test_customer_decision_prioritizes_excellent_client_with_critical_kit() -> None:
    payload = _base_context()
    payload["customer"] = {"tenure_months": 48, "active_contracts": 2, "customer_segment": "business"}
    payload["contract"]["periodic_amount_usd"] = 35
    payload["kit_intelligence"]["maintenance_risk"] = 0.9

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["client_value"] >= 75
    assert result["scores"]["operational_risk"] >= 85
    assert result["decision"]["recommended_action"] == "urgent_technical_intervention"


def test_customer_decision_keeps_bad_payer_with_healthy_kit_as_commercial_action() -> None:
    payload = _base_context()
    payload["payment"].update(
        {
            "late_payments_last_6_months": 5,
            "missed_payments_last_6_months": 2,
            "failed_payments_last_6_months": 1,
            "payment_success_rate": 0.35,
            "average_days_late": 12,
            "last_payment_status": "missed",
        }
    )
    payload["kit_intelligence"]["maintenance_risk"] = 0.12
    payload["kit_intelligence"]["security_risk"] = 0.05

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["payment_risk"] >= 70
    assert result["scores"]["operational_risk"] < 40
    assert result["decision"]["recommended_action"] == "commercial_follow_up"


def test_customer_decision_flags_important_client_with_high_operational_risk() -> None:
    payload = _base_context()
    payload["customer"] = {"tenure_months": 36, "active_contracts": 2, "customer_segment": "business"}
    payload["contract"]["periodic_amount_usd"] = 30
    payload["kit_intelligence"]["maintenance_risk"] = 0.76

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["client_value"] >= 75
    assert result["decision"]["recommended_action"] == "technical_intervention"
    assert result["decision"]["priority"] in {"high", "critical"}


def test_customer_decision_reports_missing_features_without_zeroing_silently() -> None:
    payload = _base_context()
    payload["kit_intelligence"] = {}
    payload["telemetry"] = {}
    payload["data_quality"]["missing_features"] = ["kit_intelligence.maintenance_risk"]

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["scores"]["operational_risk"] == 50
    assert "kit_intelligence" in result["data_quality"]["missing_features"]
    assert "kit_intelligence.maintenance_risk" in result["data_quality"]["missing_features"]
    assert result["data_quality"]["status"] == "partial"


def test_customer_decision_invalid_payload_schema_version_is_blocked() -> None:
    payload = _base_context()
    payload["schema_version"] = "2.0"

    result = CustomerDecisionEngine().evaluate(payload)

    assert result["identity_status"] == "invalid"
    assert result["data_quality"]["status"] == "blocked"
    assert result["decision"]["recommended_action"] == "fix_payload"


def test_customer_decision_api_endpoint_uses_injected_service(tmp_path, monkeypatch) -> None:
    class FakeService:
        def evaluate_customer_context(self, payload: dict) -> dict:
            assert payload["request_id"] == "req-test-001"
            return {"request_id": payload["request_id"], "scores": {"client_value": 70}}

    monkeypatch.setattr(api_main, "customer_scoring_service", FakeService())
    monkeypatch.setattr(api_main, "realtime_store", RealtimeTelemetryStore(tmp_path / "customer.sqlite"))

    body = api_main.customer_decision_evaluate(api_main.CustomerDecisionRequest(**_base_context()))

    assert body["request_id"] == "req-test-001"
    assert body["scores"]["client_value"] == 70
    assert body["persistence"]["stored"] is True


def test_customer_decision_contract_schemas_are_versioned() -> None:
    for filename in [
        "schemas/customer_decision_context.v1.schema.json",
        "schemas/customer_decision_result.v1.schema.json",
        "schemas/payment.v1.schema.json",
        "schemas/contract.v1.schema.json",
    ]:
        schema = json.loads(Path(filename).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"].endswith(".v1")
