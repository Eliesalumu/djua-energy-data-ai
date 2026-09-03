from __future__ import annotations

import apps.api.main as api_main
from djua_energy.scoring.dataset import generate_historical_customer_dataset
from djua_energy.scoring.conversation import CustomerRiskConversationService
from djua_energy.scoring.service import CustomerScoringService


SAMPLE_EXTERNAL_PAYLOAD = {
    "success": True,
    "data": {
        "client": {
            "accountNumber": "ACC-2026-0001",
            "firstName": "Jean-Luc",
            "lastName": "Kabila",
            "orangeMoneyAccountAgeMonths": 36,
            "estimatedIncomeUSD": 450,
            "profession": "Commercant independant",
            "historicalRiskScore": 0.12,
        },
        "subscription": {
            "kitId": "DJUA-KIN-000001",
            "offerName": "Orange Energie TV 24 + Fan",
            "status": "active",
            "paidMonthsCount": 16,
        },
        "paymentHistory": [
            {
                "paymentId": "TXN-OM-1",
                "clientPhone": "0848451555",
                "amountUSD": 25,
                "date": "2026-08-01T12:00:00.000Z",
                "status": "completed",
            }
        ],
    },
}


def test_customer_scoring_dataset_has_500_clients_and_monthly_history(tmp_path) -> None:
    dataset = generate_historical_customer_dataset(output_path=tmp_path / "history.csv")

    assert dataset["client_id"].nunique() == 500
    assert len(dataset) == 6000
    assert set(dataset["default_next_90d"].unique()).issubset({0, 1})
    assert 0 < dataset["default_next_90d"].mean() < 1


def test_customer_scoring_service_scores_external_payload() -> None:
    service = CustomerScoringService()

    result = service.score_payload(SAMPLE_EXTERNAL_PAYLOAD)

    assert 0 <= result["score"] <= 100
    assert result["risk_level"] in {"low", "medium", "high"}
    assert result["default_probability_90d"] >= 0
    assert result["model"]["version"] == "customer-scoring-synthetic-v1"
    assert result["explanation"]["provider"] == "local"
    assert result["features"]["payment_success_rate"] >= 0
    assert result["main_factors"]


def test_customer_risk_conversation_gives_detailed_local_answer(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    scoring_service = CustomerScoringService()
    scoring = scoring_service.score_payload(SAMPLE_EXTERNAL_PAYLOAD)
    chat = CustomerRiskConversationService()

    result = chat.answer("IA, que penses-tu de ce client ?", scoring, SAMPLE_EXTERNAL_PAYLOAD, use_llm=True)

    assert result["provider"] == "local"
    assert "Conclusion" in result["answer"]
    assert "Points de vigilance" in result["answer"]
    assert "Action recommandee" in result["answer"]


def test_customer_scoring_endpoint_uses_injected_service(monkeypatch) -> None:
    class FakeService:
        def score_from_external_api(self, phone: str, explain_with_llm: bool = False) -> dict:
            assert phone == "0848451555"
            assert explain_with_llm is False
            return {"phone": phone, "score": 82, "risk_level": "low"}

    monkeypatch.setattr(api_main, "customer_scoring_service", FakeService())

    body = api_main.customer_scoring("0848451555", explain_with_llm=False)

    assert body["score"] == 82
    assert body["risk_level"] == "low"
