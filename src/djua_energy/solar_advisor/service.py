from __future__ import annotations

from dataclasses import asdict
from hashlib import sha1
from typing import Any

from djua_energy.solar_advisor.catalog import ApplianceCatalog, ComponentCatalog, public_rows
from djua_energy.solar_advisor.ai_assistant import SolarAdvisorAI
from djua_energy.solar_advisor.consumption_engine import ConsumptionEngine
from djua_energy.solar_advisor.conversation_engine import ConversationEngine
from djua_energy.solar_advisor.explanation_engine import ExplanationEngine
from djua_energy.solar_advisor.quote_service import QuoteService
from djua_energy.solar_advisor.repository import SolarAdvisorRepository
from djua_energy.solar_advisor.schemas import AdvisorRequest, ApplianceNeed
from djua_energy.solar_advisor.sizing_engine import SizingEngine


class SolarAdvisorService:
    def __init__(
        self,
        appliance_catalog: ApplianceCatalog | None = None,
        component_catalog: ComponentCatalog | None = None,
        repository: SolarAdvisorRepository | None = None,
    ) -> None:
        self.appliance_catalog = appliance_catalog or ApplianceCatalog()
        self.component_catalog = component_catalog or ComponentCatalog()
        self.consumption_engine = ConsumptionEngine(self.appliance_catalog)
        self.sizing_engine = SizingEngine(self.component_catalog)
        self.explanation_engine = ExplanationEngine()
        self.conversation_engine = ConversationEngine()
        self.quote_service = QuoteService()
        self.repository = repository or SolarAdvisorRepository()
        self.ai_assistant = SolarAdvisorAI()

    def recommend(self, payload: dict[str, Any], *, save: bool = True) -> dict[str, Any]:
        request = self._request_from_payload(payload)
        consumption = self.consumption_engine.calculate(request)
        sizing, selected, alternatives = self.sizing_engine.size(request, consumption)
        counts = {
            "panel": sizing.panel_count,
            "battery": sizing.battery_count,
            "inverter": 1,
            "controller": 1,
        }
        recommendation_id = self._recommendation_id(request, consumption.adjusted_daily_energy_wh)
        quote = self.quote_service.build_quote(recommendation_id, selected, counts)
        missing = self.missing_information(request)
        result = {
            "recommendation_id": recommendation_id,
            "module": "DJUA AI Solar Advisor",
            "status": "recommendation_ready" if not missing else "recommendation_with_assumptions",
            "request": asdict(request),
            "consumption": asdict(consumption),
            "sizing": asdict(sizing),
            "selected_components": selected,
            "alternatives": alternatives,
            "explanation": self.explanation_engine.explain(request, consumption, sizing),
            "quote": quote,
            "missing_information": missing,
            "assumptions": self._assumptions(consumption),
            "limitations": [
                "Catalogue composants synthetique pour le MVP.",
                "Les prix doivent etre remplaces par les donnees commerciales officielles Orange Energy.",
                "La recommandation doit etre validee par un technicien avant installation reelle.",
            ],
            "integration_links": {
                "future_customer_scoring_key": request.customer_id,
                "future_iot_baseline": {
                    "expected_daily_energy_wh": consumption.total_daily_energy_wh,
                    "expected_peak_power_w": consumption.simultaneous_power_w,
                    "recommended_pv_power_w": sizing.pv_total_power_w,
                },
            },
        }
        if save:
            self.repository.save_recommendation(result)
        return result

    def conversation_step(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        ai_turn = self.ai_assistant.conversation_turn(message, context)
        if ai_turn.get("used_ai"):
            request_payload = self._merge_conversation_context(context, ai_turn.get("request_updates", {}))
        else:
            local_request = self.conversation_engine.extract(message, context)
            request_payload = self._merge_conversation_context(context, asdict(local_request))
        
        request = self._request_from_conversation_context(request_payload)
        questions = self.conversation_engine.next_questions(request)
        has_appliances = bool(request.appliances)
        
        # If user gave appliances, we can immediately produce a recommendation
        can_recommend = has_appliances
        recommendation = None
        if can_recommend:
            recommendation = self.recommend(asdict(request), save=True)

        # Generate responsive assistant message
        if ai_turn.get("used_ai") and ai_turn.get("assistant_message"):
            assistant_msg = ai_turn.get("assistant_message")
        elif has_appliances and recommendation:
            app_summary = ", ".join(f"{a.quantity}x {a.name}" for a in request.appliances)
            sizing = recommendation["sizing"]
            quote = recommendation["quote"]
            consumption = recommendation["consumption"]
            autonomy_str = f"{int(request.autonomy_hours)}h" if request.autonomy_hours else "10h"
            budget_str = f" (budget cible: {int(request.budget):,} XAF)".replace(",", " ") if request.budget else ""
            monthly_str = f"{int(quote['total_estimated'] / 24):,}".replace(",", " ")
            total_str = f"{int(quote['total_estimated']):,}".replace(",", " ")
            
            assistant_msg = (
                f"Parfait ! J'ai bien analysé vos besoins : **{app_summary}**{budget_str}.\n\n"
                f"• **Consommation estimée** : {consumption['total_daily_energy_kwh']} kWh / jour (puissance de pointe : {int(consumption['simultaneous_power_w'])} W).\n"
                f"• **Kit dimensionné** : {sizing['panel_count']} panneau(x) de {sizing['panel_power_w']} Wc ({sizing['pv_total_power_w']} Wc total), "
                f"{sizing['battery_count']} batterie(s) {sizing['battery_technology']} ({sizing['battery_capacity_wh']} Wh utiles, autonomie {sizing['autonomy_hours_estimated']}h) "
                f"et 1 onduleur {sizing['inverter_power_w']} W.\n"
                f"• **Devis indicatif** : **{total_str} {quote['currency']}** (soit env. **{monthly_str} {quote['currency']} / mois** en formule Pay-As-You-Go 24 mois).\n\n"
                f"Le devis complet est généré et synchronisé !"
            )
        else:
            assistant_msg = (
                "Bonjour ! Je suis DJUA AI Solar Advisor. Décrivez-moi simplement les appareils que vous souhaitez alimenter "
                "(ex: *'j'ai 8 ampoules, une télé 32 pouces, 1 congélateur et je veux 8h d'autonomie'*)."
            )

        response = {
            "assistant_message": assistant_msg,
            "request": asdict(request),
            "next_questions": questions,
            "can_recommend": can_recommend,
            "used_ai": ai_turn.get("used_ai", False),
            "model": ai_turn.get("model"),
            "warning": ai_turn.get("warning"),
        }
        if recommendation:
            response["recommendation"] = recommendation
        return response

    def create_contact_request(self, recommendation_id: str, contact: dict[str, Any]) -> dict[str, Any]:
        if self.repository.get_recommendation(recommendation_id) is None:
            raise ValueError("recommendation not found")
        return self.repository.save_contact_request(recommendation_id, contact)

    def explain_with_ai(self, recommendation_id: str, audience: str = "client") -> dict[str, Any]:
        recommendation = self.repository.get_recommendation(recommendation_id)
        if recommendation is None:
            raise ValueError("recommendation not found")
        return self.ai_assistant.explain_recommendation(recommendation, audience=audience)

    def answer_question(self, recommendation_id: str, question: str) -> dict[str, Any]:
        recommendation = self.repository.get_recommendation(recommendation_id)
        if recommendation is None:
            raise ValueError("recommendation not found")
        return self.ai_assistant.answer_question(recommendation, question)

    def present_quote_with_ai(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        return self.ai_assistant.present_quote(recommendation)

    def get_recommendation(self, recommendation_id: str) -> dict[str, Any] | None:
        return self.repository.get_recommendation(recommendation_id)

    def list_recommendations(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.repository.list_recommendations(limit)

    def catalogs(self) -> dict[str, Any]:
        return {
            "appliances": public_rows(self.appliance_catalog.items),
            "components": public_rows(self.component_catalog.components),
            "notice": "Catalogues de demonstration. Les donnees officielles Orange Energy peuvent remplacer ces CSV.",
        }

    def missing_information(self, request: AdvisorRequest) -> list[str]:
        missing = []
        if not request.city and not request.region:
            missing.append("city_or_region")
        if not request.autonomy_hours:
            missing.append("autonomy_hours")
        for appliance in request.appliances:
            if appliance.power_w is None and self.appliance_catalog.find(appliance.name, appliance.appliance_id) is None:
                missing.append(f"power_w:{appliance.name}")
        return missing

    def _request_from_payload(self, payload: dict[str, Any]) -> AdvisorRequest:
        appliances = [
            item if isinstance(item, ApplianceNeed) else ApplianceNeed(**item)
            for item in payload.get("appliances", [])
        ]
        if not appliances:
            raise ValueError("at least one appliance is required")
        return AdvisorRequest(
            customer_id=payload.get("customer_id"),
            city=payload.get("city"),
            region=payload.get("region"),
            housing_type=payload.get("housing_type"),
            people_count=payload.get("people_count"),
            autonomy_hours=payload.get("autonomy_hours"),
            budget=payload.get("budget"),
            preference=payload.get("preference", "balanced"),
            appliances=appliances,
            source=payload.get("source", "manual"),
            contact=payload.get("contact", {}),
        )

    def _request_from_conversation_context(self, payload: dict[str, Any]) -> AdvisorRequest:
        appliances = []
        for item in payload.get("appliances", []):
            if isinstance(item, ApplianceNeed):
                appliances.append(item)
            elif isinstance(item, dict) and item.get("name"):
                appliances.append(ApplianceNeed(**item))
        return AdvisorRequest(
            customer_id=payload.get("customer_id"),
            city=payload.get("city"),
            region=payload.get("region"),
            housing_type=payload.get("housing_type"),
            people_count=payload.get("people_count"),
            autonomy_hours=payload.get("autonomy_hours"),
            budget=payload.get("budget"),
            preference=payload.get("preference", "balanced") or "balanced",
            appliances=appliances,
            source=payload.get("source", "conversation"),
            contact=payload.get("contact", {}),
        )

    def _merge_conversation_context(self, context: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(context or {})
        for key, value in (updates or {}).items():
            if key == "appliances":
                existing = self._deduplicate_appliances(list(merged.get("appliances") or []))
                for item in value or []:
                    if isinstance(item, dict) and item.get("name"):
                        existing = self._upsert_appliance(existing, {k: v for k, v in item.items() if v is not None})
                merged["appliances"] = self._deduplicate_appliances(existing)
            elif value is not None and value != "" and value != []:
                merged[key] = value
        return merged

    def _upsert_appliance(self, appliances: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
        key = self._appliance_key(item)
        for index, existing in enumerate(appliances):
            if self._appliance_key(existing) == key:
                merged = dict(existing)
                for field, value in item.items():
                    if value is not None and value != "":
                        merged[field] = value
                appliances[index] = merged
                return appliances
        appliances.append(item)
        return appliances

    def _deduplicate_appliances(self, appliances: list[Any]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        for item in appliances:
            if isinstance(item, ApplianceNeed):
                item = asdict(item)
            if isinstance(item, dict) and item.get("name"):
                deduped = self._upsert_appliance(deduped, item)
        return deduped

    def _appliance_key(self, item: dict[str, Any]) -> str:
        appliance_id = item.get("appliance_id")
        if appliance_id:
            return str(appliance_id).lower()
        return str(item.get("name", "")).lower().strip()

    def _client_explicitly_requested_quote(self, message: str) -> bool:
        text = message.lower()
        triggers = [
            "devis",
            "donne moi",
            "donnez moi",
            "fais le calcul",
            "calcule",
            "recommande",
            "dimensionne",
            "c'est bon",
            "cest bon",
        ]
        return any(trigger in text for trigger in triggers)

    def _recommendation_id(self, request: AdvisorRequest, adjusted_energy: float) -> str:
        key = repr(asdict(request)) + str(round(adjusted_energy, 2))
        return "solar-rec-" + sha1(key.encode("utf-8")).hexdigest()[:12]

    def _assumptions(self, consumption) -> list[str]:
        assumptions = []
        for appliance in consumption.appliances:
            assumptions.extend(appliance.assumptions)
        assumptions.append("Dimensionnement calcule avec pertes systeme, marge de croissance et marge d'incertitude.")
        return assumptions
