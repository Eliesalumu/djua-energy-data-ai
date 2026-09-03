from pathlib import Path

import apps.api.main as api_main
from djua_energy.solar_advisor.repository import SolarAdvisorRepository
from djua_energy.solar_advisor.service import SolarAdvisorService


def _payload() -> dict:
    return {
        "customer_id": "client-test",
        "city": "kinshasa",
        "housing_type": "menage",
        "people_count": 5,
        "autonomy_hours": 10,
        "budget": 1800000,
        "preference": "balanced",
        "appliances": [
            {"name": "television", "appliance_id": "television_led_32", "quantity": 1, "hours_per_day": 5, "usage_period": "night"},
            {"name": "congelateur", "appliance_id": "freezer_small", "quantity": 1, "hours_per_day": 24, "essential": True},
            {"name": "ampoule", "appliance_id": "led_bulb_9w", "quantity": 8, "hours_per_day": 6, "usage_period": "night"},
            {"name": "ventilateur", "appliance_id": "fan_table", "quantity": 2, "hours_per_day": 8, "usage_period": "night"},
        ],
    }


def test_solar_advisor_recommends_complete_configuration(tmp_path: Path) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))

    result = service.recommend(_payload())

    assert result["module"] == "DJUA AI Solar Advisor"
    assert result["consumption"]["total_daily_energy_wh"] > 0
    assert result["sizing"]["panel_count"] >= 1
    assert result["sizing"]["battery_count"] >= 1
    assert result["sizing"]["inverter_power_w"] >= result["consumption"]["simultaneous_power_w"] * 0.8
    assert result["selected_components"]["panel"]["is_synthetic"] is True
    assert result["quote"]["items"]
    assert service.get_recommendation(result["recommendation_id"])["recommendation_id"] == result["recommendation_id"]


def test_solar_advisor_handles_unknown_appliance_with_warning(tmp_path: Path) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))
    payload = _payload()
    payload["appliances"] = [{"name": "machine inconnue", "quantity": 1, "hours_per_day": 2}]

    result = service.recommend(payload)

    assert "power_w:machine inconnue" in result["missing_information"]
    assert result["consumption"]["warnings"]
    assert result["assumptions"]


def test_solar_advisor_conversation_extracts_needs(tmp_path: Path) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))

    first = service.conversation_step(
        "Je suis a Kinshasa avec 1 television, 1 congelateur, 8 ampoules, 2 ventilateurs et 10 heures autonomie"
    )
    result = service.conversation_step("fais le devis", first["request"])

    assert result["request"]["city"] == "kinshasa"
    assert result["request"]["appliances"]
    assert result["can_recommend"] is True
    assert result["recommendation"]["sizing"]["pv_total_power_w"] > 0


def test_solar_advisor_conversation_answers_identity_question(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))

    result = service.conversation_step("tu es qui?", {})

    assert "DJUA AI Solar Advisor" in result["assistant_message"]
    assert "tranquillement" in result["assistant_message"]
    assert result["can_recommend"] is False
    assert result["request"]["appliances"] == []


def test_solar_advisor_conversation_does_not_duplicate_ai_appliances(tmp_path: Path, monkeypatch) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))

    turns = [
        {
            "assistant_message": "Je suis DJUA AI Solar Advisor. Je vous aide a choisir un kit solaire.",
            "request_updates": {},
            "ready_for_quote": False,
            "used_ai": True,
            "model": "fake",
            "warning": None,
        },
        {
            "assistant_message": "J'ai note une TV 32 pouces, un congelateur, 10h d'autonomie et Kinshasa.",
            "request_updates": {
                "city": "kinshasa",
                "autonomy_hours": 10,
                "appliances": [
                    {
                        "name": "television 32 pouces",
                        "appliance_id": "television_led_32",
                        "quantity": 1,
                        "hours_per_day": 5,
                        "usage_period": "night",
                    },
                    {
                        "name": "congelateur samsung 250 litres",
                        "appliance_id": "freezer_small",
                        "quantity": 1,
                        "hours_per_day": 24,
                        "usage_period": "continuous",
                    },
                ],
            },
            "ready_for_quote": False,
            "used_ai": True,
            "model": "fake",
            "warning": None,
        },
        {
            "assistant_message": "Je prepare le devis.",
            "request_updates": {
                "people_count": 5,
                "housing_type": "logement modeste",
                "budget": 20,
            },
            "ready_for_quote": True,
            "used_ai": True,
            "model": "fake",
            "warning": None,
        },
    ]

    class FakeAI:
        def conversation_turn(self, message, context):
            return turns.pop(0)

        def explain_recommendation(self, recommendation, audience="client"):
            return {"used_ai": True, "model": "fake", "explanation": "ok", "warning": None}

    service.ai_assistant = FakeAI()

    first = service.conversation_step("tu es qui?", {})
    second = service.conversation_step(
        "Une tele de 32 pouces et un congelateur samsung de 250 litres 10 heures autonomie je suis a kinshasa",
        first["request"],
    )
    third = service.conversation_step(
        "5 personnes logement modeste budget 20 dollars le mois. non c'est bon donne moi le devis",
        second["request"],
    )

    assert third["can_recommend"] is True
    assert len(third["request"]["appliances"]) == 2
    assert third["recommendation"]["consumption"]["total_daily_energy_kwh"] < 2


def test_solar_advisor_does_not_quote_when_ai_is_still_asking_question(tmp_path: Path) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))

    class FakeAI:
        def conversation_turn(self, message, context):
            return {
                "assistant_message": "Merci. Est-ce que vos ampoules sont LED ?",
                "request_updates": {
                    "city": "kinshasa",
                    "appliances": [
                        {
                            "name": "television samsung 32 pouces",
                            "appliance_id": "television_led_32",
                            "quantity": 1,
                            "hours_per_day": 10,
                        }
                    ],
                },
                "ready_for_quote": True,
                "used_ai": True,
                "model": "fake",
                "warning": None,
            }

    service.ai_assistant = FakeAI()

    result = service.conversation_step("J'ai aussi deux ampoules et je suis a kinshasa", {})

    assert result["can_recommend"] is False
    assert "recommendation" not in result


def test_solar_advisor_contact_request_is_persisted(tmp_path: Path) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))
    result = service.recommend(_payload())

    contact = service.create_contact_request(
        result["recommendation_id"],
        {"name": "Client Test", "phone": "+242000000"},
    )

    assert contact["status"] == "pending"
    assert contact["recommendation_id"] == result["recommendation_id"]


def test_solar_advisor_ai_explanation_has_local_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))
    result = service.recommend(_payload())

    explanation = service.explain_with_ai(result["recommendation_id"])

    assert explanation["used_ai"] is False
    assert "OPENAI_API_KEY" in explanation["warning"]
    assert str(result["sizing"]["panel_count"]) in explanation["explanation"]


def test_solar_advisor_answer_question_with_local_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))
    result = service.recommend(_payload())

    answer = service.answer_question(result["recommendation_id"], "Pourquoi me conseillez-vous ce nombre de panneaux ?")

    assert answer["used_ai"] is False
    assert "panneau" in answer["answer"].lower()
    assert str(result["sizing"]["panel_count"]) in answer["answer"]


def test_solar_advisor_api_endpoints(monkeypatch, tmp_path: Path) -> None:
    service = SolarAdvisorService(repository=SolarAdvisorRepository(tmp_path / "advisor.sqlite"))
    monkeypatch.setattr(api_main, "solar_advisor_service", service)

    body = api_main.solar_advisor_recommend(api_main.SolarAdvisorRequest(**_payload()))
    listing = api_main.solar_advisor_recommendations()
    detail = api_main.solar_advisor_recommendation_detail(body["recommendation_id"])
    contact = api_main.solar_advisor_contact(
        body["recommendation_id"],
        api_main.SolarContactRequest(name="Client API", phone="+242111"),
    )
    explanation = api_main.solar_advisor_explain(
        body["recommendation_id"],
        api_main.SolarExplanationRequest(audience="client"),
    )
    question_resp = api_main.solar_advisor_ask(
        body["recommendation_id"],
        api_main.SolarQuestionRequest(question="Quelle autonomie pour la batterie ?"),
    )

    assert body["recommendation_id"]
    assert listing["recommendations"]
    assert detail["recommendation_id"] == body["recommendation_id"]
    assert contact["status"] == "pending"
    assert "explanation" in explanation
    assert "answer" in question_resp


def test_solar_catalog_endpoint_exposes_synthetic_notice() -> None:
    catalogs = api_main.solar_advisor_catalogs()

    assert catalogs["appliances"]
    assert catalogs["components"]
    assert "officielles" in catalogs["notice"]

