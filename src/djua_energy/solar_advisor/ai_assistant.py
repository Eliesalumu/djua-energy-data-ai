from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SolarAdvisorAI:
    """Optional OpenAI-backed assistant for explanations.

    The deterministic recommendation engine remains the source of truth.
    This helper only reformulates results and guides the conversation.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("DJUA_OPENAI_MODEL", "gpt-4o-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def explain_recommendation(self, recommendation: dict[str, Any], audience: str = "client") -> dict[str, Any]:
        local_fallback = self._local_explanation(recommendation)
        if not self.enabled:
            return {
                "used_ai": False,
                "model": None,
                "explanation": local_fallback,
                "warning": "OPENAI_API_KEY non configuree: explication locale utilisee.",
            }

        prompt = self._build_explanation_prompt(recommendation, audience)
        try:
            text = self._call_responses_api(prompt)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return {
                "used_ai": False,
                "model": self.model,
                "explanation": local_fallback,
                "warning": f"Explication IA indisponible: {exc.__class__.__name__}. Fallback local utilise.",
            }
        return {
            "used_ai": True,
            "model": self.model,
            "explanation": text,
            "warning": "L'IA reformule uniquement. Les calculs viennent du moteur deterministe.",
        }

    def answer_question(self, recommendation: dict[str, Any], question: str) -> dict[str, Any]:
        local_fallback = self._local_answer_question(recommendation, question)
        if not self.enabled:
            return {
                "used_ai": False,
                "model": None,
                "answer": local_fallback,
                "warning": "OPENAI_API_KEY non configuree: reponse locale basee sur les donnees du devis.",
            }

        prompt = self._build_question_prompt(recommendation, question)
        try:
            text = self._call_responses_api(
                prompt,
                system=(
                    "Tu es DJUA AI Solar Advisor. Tu reponds aux questions du client sur son devis solaire calcule. "
                    "Tu es bienveillant, precis et pedagogique. Tu t'appuies STRICTEMENT sur les donnees du devis fournies "
                    "(consommation, nombre de panneaux, puissance en W, capacite batterie en Wh, prix XAF, autonomie en heures). "
                    "Ne contredis jamais les chiffres du devis."
                ),
                max_output_tokens=750,
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return {
                "used_ai": False,
                "model": self.model,
                "answer": local_fallback,
                "warning": f"Assistant IA indisponible ({exc.__class__.__name__}): reponse locale utilisee.",
            }
        return {
            "used_ai": True,
            "model": self.model,
            "answer": text,
            "warning": "Reponse generee par IA fondee sur les donnees reelles du devis.",
        }

    def present_quote(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        local = self._local_quote_presentation(recommendation)
        if not self.enabled:
            return {
                "used_ai": False,
                "model": None,
                "message": local,
                "warning": "OPENAI_API_KEY non configuree: presentation locale utilisee.",
            }
        prompt = (
            "Presente ce devis solaire au client dans le meme ton chaleureux que la conversation. "
            "Ne montre pas de JSON, pas de tableau technique brut. "
            "Explique simplement: consommation, panneaux, batterie, onduleur, autonomie, prix demo, infos a confirmer. "
            "Ne change aucun chiffre. Termine en demandant s'il veut une explication plus detaillee ou une demande de contact.\n\n"
            + json.dumps(
                {
                    "request": recommendation.get("request"),
                    "consumption": recommendation.get("consumption"),
                    "sizing": recommendation.get("sizing"),
                    "quote": recommendation.get("quote"),
                    "missing_information": recommendation.get("missing_information"),
                    "limitations": recommendation.get("limitations"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        try:
            message = self._call_responses_api(
                prompt,
                system=(
                    "Tu es DJUA AI Solar Advisor. Tu presentes un devis solaire avec chaleur, clarte et prudence. "
                    "Tu ne modifies jamais les calculs."
                ),
                max_output_tokens=800,
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return {
                "used_ai": False,
                "model": self.model,
                "message": local,
                "warning": f"Presentation IA indisponible: {exc.__class__.__name__}. Fallback local utilise.",
            }
        return {
            "used_ai": True,
            "model": self.model,
            "message": message,
            "warning": "Presentation generee par IA a partir du calcul deterministe.",
        }

    def conversation_turn(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        fallback = self._local_conversation_turn(message, context)
        if not self.enabled:
            fallback["used_ai"] = False
            fallback["model"] = None
            fallback["warning"] = "OPENAI_API_KEY non configuree: assistant local utilise."
            return fallback
        prompt = self._build_conversation_prompt(message, context)
        try:
            text = self._call_responses_api(
                prompt,
                system=(
                    "Tu es DJUA AI Solar Advisor, un assistant conversationnel Orange Energy chaleureux et rassurant. "
                    "Tu parles comme un conseiller humain: simple, patient, accueillant, jamais froid ni trop formel. "
                    "Tu mets le client a l'aise, surtout s'il ne connait rien au solaire. "
                    "Tu peux dire que les approximations sont acceptables au debut et que tu aideras a confirmer ensuite. "
                    "Tu restes sobre: pas de blagues inutiles, pas de familiarite excessive, pas de promesses commerciales. "
                    "Tu aides le client a decrire ses appareils pour recommander un kit solaire. "
                    "Tu peux repondre aux questions generales, mais tu ne dimensionnes jamais toi-meme. "
                    "Quand tu extrais des donnees, retourne uniquement un JSON valide avec les champs demandes."
                ),
                max_output_tokens=900,
            )
            parsed = self._parse_json_object(text)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            parsed = fallback
            parsed["used_ai"] = False
            parsed["model"] = self.model
            parsed["warning"] = "Assistant IA indisponible ou reponse non JSON: assistant local utilise."
            return parsed
        parsed.setdefault("request_updates", {})
        parsed.setdefault("ready_for_quote", False)
        parsed.setdefault("needs_manual_entry", False)
        parsed["used_ai"] = True
        parsed["model"] = self.model
        parsed["warning"] = "L'IA guide le dialogue; le devis vient du moteur deterministe."
        return parsed

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                return json.loads(cleaned[start : end + 1])
            raise

    def _call_responses_api(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_output_tokens: int = 700,
    ) -> str:
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": system
                    or (
                        "Tu es un conseiller Orange Energy. Explique simplement une recommandation solaire. "
                        "Ne modifie jamais les chiffres. Signale que les prix sont de demonstration si c'est indique."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_output_tokens": max_output_tokens,
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        return self._extract_text(body)

    def _extract_text(self, body: dict[str, Any]) -> str:
        if body.get("output_text"):
            return str(body["output_text"])
        chunks: list[str] = []
        for item in body.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(str(content["text"]))
        if chunks:
            return "\n".join(chunks)
        raise ValueError("OpenAI response did not contain text")

    def _build_explanation_prompt(self, recommendation: dict[str, Any], audience: str) -> str:
        compact = {
            "audience": audience,
            "request": recommendation.get("request"),
            "consumption": recommendation.get("consumption"),
            "sizing": recommendation.get("sizing"),
            "quote": recommendation.get("quote"),
            "limitations": recommendation.get("limitations"),
        }
        return (
            "Explique cette recommandation solaire en francais simple. "
            "Structure: besoin client, calcul de consommation, panneaux, batteries, onduleur, devis, limites, prochaine action. "
            "Ne change aucun chiffre.\n\n"
            + json.dumps(compact, ensure_ascii=False, indent=2)
        )

    def _build_conversation_prompt(self, message: str, context: dict[str, Any]) -> str:
        return (
            "Reponds comme un vrai assistant conversationnel, puis extrais les informations utiles. "
            "Ton message doit etre accueillant, clair et rassurant. "
            "Evite le jargon. Si le client semble perdu, dis-lui qu'on va avancer petit a petit. "
            "Ne sois ni trop solennel, ni trop amusant: inspire confiance. "
            "Si le client demande qui tu es, explique ton role. "
            "Si le client donne des appareils, ajoute-les dans request_updates.appliances. "
            "Utilise ces appliance_id quand c'est pertinent: television_led_32 pour TV/tele 32 pouces, "
            "freezer_small pour congelateur, fridge_efficient pour refrigerateur/frigo, led_bulb_9w pour ampoule, "
            "fan_table pour ventilateur, phone_charger pour telephone, laptop pour ordinateur portable. "
            "Pour un congelateur ou refrigerateur, mets hours_per_day=24 et usage_period=continuous sauf indication contraire. "
            "Mets ready_for_quote=true uniquement si le dernier message du client demande clairement le devis, "
            "par exemple 'donne moi le devis', 'fais le devis', 'calcule maintenant', et si au moins un appareil est connu. "
            "Si tu viens de poser une question au client, ready_for_quote doit rester false. "
            "Si des informations manquent, pose une question naturelle. "
            "Retourne strictement ce JSON, sans markdown:\n"
            "{\n"
            '  "assistant_message": "message en francais",\n'
            '  "request_updates": {\n'
            '    "city": null,\n'
            '    "region": null,\n'
            '    "housing_type": null,\n'
            '    "people_count": null,\n'
            '    "autonomy_hours": null,\n'
            '    "budget": null,\n'
            '    "preference": null,\n'
            '    "appliances": [{"name": "string", "appliance_id": "string ou null", "quantity": 1, "hours_per_day": null, "power_w": null, "usage_period": "mixed", "essential": true}]\n'
            "  },\n"
            '  "ready_for_quote": false,\n'
            '  "needs_manual_entry": false\n'
            "}\n\n"
            "Contexte actuel:\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
            + "\n\nMessage client:\n"
            + message
        )

    def _local_explanation(self, recommendation: dict[str, Any]) -> str:
        sizing = recommendation["sizing"]
        consumption = recommendation["consumption"]
        quote = recommendation["quote"]
        return (
            f"Le besoin declare consomme environ {consumption['total_daily_energy_kwh']} kWh par jour. "
            f"Le moteur ajoute une marge pour eviter un kit trop juste. "
            f"La configuration propose {sizing['panel_count']} panneau(x) de {sizing['panel_power_w']} W, "
            f"{sizing['battery_count']} batterie(s) et un onduleur de {sizing['inverter_power_w']} W. "
            f"L'autonomie estimee est de {sizing['autonomy_hours_estimated']} heures. "
            f"Le devis de demonstration est de {quote['total_estimated']} {quote['currency']}. "
            "Les prix et composants doivent etre valides avec le catalogue officiel Orange Energy."
        )

    def _local_conversation_turn(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        text = message.lower()
        if any(phrase in text for phrase in ["tu es qui", "qui es tu", "c'est quoi", "a quoi tu sers"]):
            return {
                "assistant_message": (
                    "Je suis DJUA AI Solar Advisor. Je suis la pour vous aider tranquillement a trouver le kit solaire "
                    "qui correspond a vos besoins. Vous n'avez pas besoin de tout connaitre: on liste les appareils ensemble, "
                    "meme avec des estimations, puis je lance un calcul fiable pour proposer panneaux, batteries, onduleur et devis."
                ),
                "request_updates": {},
                "ready_for_quote": False,
                "needs_manual_entry": False,
            }
        if any(word in text for word in ["devis", "recommande", "calcul", "dimensionne"]):
            return {
                "assistant_message": "D'accord, je peux preparer le devis si les appareils sont deja renseignes.",
                "request_updates": {},
                "ready_for_quote": True,
                "needs_manual_entry": False,
            }
        return {
            "assistant_message": (
                "Pas de souci, on peut avancer simplement. Dites-moi les appareils a alimenter, meme approximativement: "
                "leur quantite et, si vous savez, le nombre d'heures d'utilisation par jour. "
                "Par exemple: 1 television 5h, 1 congelateur 24h, 8 ampoules 6h."
            ),
            "request_updates": {},
            "ready_for_quote": False,
            "needs_manual_entry": False,
        }

    def _local_quote_presentation(self, recommendation: dict[str, Any]) -> str:
        sizing = recommendation["sizing"]
        consumption = recommendation["consumption"]
        quote = recommendation["quote"]
        missing = recommendation.get("missing_information") or []
        message = (
            "Merci, j'ai assez d'elements pour faire une premiere estimation. "
            f"Pour les appareils indiques, la consommation est d'environ {consumption['total_daily_energy_kwh']} kWh par jour. "
            f"Le moteur recommande {sizing['panel_count']} panneau(x) de {sizing['panel_power_w']} W, "
            f"{sizing['battery_count']} batterie(s), et un onduleur de {sizing['inverter_power_w']} W. "
            f"L'autonomie estimee est d'environ {sizing['autonomy_hours_estimated']} heures. "
            f"Le devis de demonstration est de {quote['total_estimated']} {quote['currency']}."
        )
        if missing:
            message += " Il reste quelques informations a confirmer: " + ", ".join(missing) + "."
        message += " Les prix sont des prix de demonstration et devront etre valides avec Orange Energy."
        return message

    def _build_question_prompt(self, recommendation: dict[str, Any], question: str) -> str:
        compact = {
            "request": recommendation.get("request"),
            "consumption": recommendation.get("consumption"),
            "sizing": recommendation.get("sizing"),
            "quote": recommendation.get("quote"),
            "assumptions": recommendation.get("assumptions"),
            "limitations": recommendation.get("limitations"),
        }
        return (
            "Voici les donnees techniques et financieres completes du devis solaire calcule pour ce client:\n\n"
            + json.dumps(compact, ensure_ascii=False, indent=2)
            + f"\n\nQuestion posee par le client:\n« {question} »\n\n"
            "Reponds clairement en francais a la question en te basant sur les donnees reelles ci-dessus. "
            "Explique simplement la logique technique, utilise les vrais chiffres du devis et rassure le client."
        )

    def _local_answer_question(self, recommendation: dict[str, Any], question: str) -> str:
        q = question.lower()
        sizing = recommendation.get("sizing", {})
        consumption = recommendation.get("consumption", {})
        quote = recommendation.get("quote", {})
        
        if any(w in q for w in ["panneau", "pv", "soleil", "combien de panneau", "pourquoi"]):
            return (
                f"Nous recommandons {sizing.get('panel_count', 1)} panneau(x) de {sizing.get('panel_power_w', 0)} W "
                f"(soit une puissance solaire totale de {sizing.get('pv_total_power_w', 0)} Wc). "
                f"Ce dimensionnement permet de produire environ {consumption.get('adjusted_daily_energy_wh', 0)} Wh/jour "
                f"en tenant compte d'un ensoleillement utile moyen (4.5h) et d'une marge de securite de 20% pour les jours nuageux."
            )
        if any(w in q for w in ["batterie", "autonomie", "nuit", "stockage", "coupure"]):
            return (
                f"Le kit comprend {sizing.get('battery_count', 1)} batterie(s) ({sizing.get('battery_technology', 'LiFePO4')}) "
                f"pour une capacite utile de {sizing.get('battery_capacity_wh', 0)} Wh. "
                f"Elle assure une autonomie estimee a {sizing.get('autonomy_hours_estimated', 10)} heures "
                f"afin d'alimenter vos appareils essentiels meme la nuit ou lors de coupures prolongees."
            )
        if any(w in q for w in ["prix", "cout", "budget", "cher", "payer", "mensualite", "payg"]):
            return (
                f"Le montant total estime de cette installation est de {quote.get('total_estimated', 0):,} {quote.get('currency', 'XAF')}. "
                f"Ce devis comprend les panneaux, la batterie, l'onduleur de {sizing.get('inverter_power_w', 0)} W, "
                f"le regulateur de charge ainsi que le kit complet de cables et protections. "
                f"Des facilites de paiement echelonne (Pay-As-You-Go) sont envisageables selon l'offre Orange Energy."
            )
        if any(w in q for w in ["pluie", "saison", "meteo", "nuage", "hiver"]):
            return (
                f"Une marge de securite de 20% a ete integree a vos besoins "
                f"(basee sur {consumption.get('total_daily_energy_kwh', 0)} kWh/jour reels portes a {consumption.get('adjusted_daily_energy_wh', 0)} Wh/j). "
                f"Le parc de batteries ({sizing.get('battery_capacity_wh', 0)} Wh) prend le relais lors des journees pluvieuses ou couvertes."
            )
        if any(w in q for w in ["ajouter", "plus", "fer", "clim", "congelateur", "frigo"]):
            return (
                f"Votre onduleur actuel de {sizing.get('inverter_power_w', 0)} W (pointes a {sizing.get('inverter_surge_power_w', 0)} W) "
                f"est calcule pour une puissance simultanee de {consumption.get('simultaneous_power_w', 0)} W. "
                f"L'ajout d'appareils a forte puissance (climatiseur, fer) necessitera d'augmenter le nombre de panneaux et la puissance de l'onduleur."
            )
        return (
            f"Votre installation est dimensionnee pour {consumption.get('total_daily_energy_kwh', 0)} kWh/jour "
            f"avec {sizing.get('panel_count', 1)} panneau(x) ({sizing.get('pv_total_power_w', 0)} Wc), "
            f"{sizing.get('battery_count', 1)} batterie(s) ({sizing.get('autonomy_hours_estimated', 10)}h d'autonomie) "
            f"pour un montant de {quote.get('total_estimated', 0):,} {quote.get('currency', 'XAF')}. "
            f"Un technicien validera avec vous les details avant la pose."
        )

