from __future__ import annotations

import json
import os
from typing import Any


class CustomerRiskConversationService:
    def answer(
        self,
        question: str,
        scoring_result: dict[str, Any],
        external_payload: dict[str, Any],
        use_llm: bool = True,
        require_llm: bool = False,
    ) -> dict[str, Any]:
        if use_llm and os.getenv("OPENAI_API_KEY"):
            try:
                return self._answer_with_openai(question, scoring_result, external_payload)
            except Exception as exc:
                if require_llm:
                    raise RuntimeError(f"OpenAI requis mais indisponible: {exc}") from exc
                local = self._answer_locally(question, scoring_result, external_payload)
                local["warning"] = f"OpenAI indisponible, reponse locale utilisee: {exc}"
                return local
        if use_llm and require_llm:
            raise RuntimeError("OpenAI requis mais OPENAI_API_KEY est absente des variables d'environnement.")
        local = self._answer_locally(question, scoring_result, external_payload)
        if use_llm:
            local["warning"] = "OPENAI_API_KEY absente: reponse conversationnelle locale utilisee."
        return local

    def _answer_with_openai(
        self,
        question: str,
        scoring_result: dict[str, Any],
        external_payload: dict[str, Any],
    ) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI()
        context = self._llm_safe_context(scoring_result)
        response = client.responses.create(
            model=os.getenv("DJUA_OPENAI_MODEL", "gpt-5-mini"),
            instructions=(
                "Tu es l'IA conversationnelle risque client de DJUA ENERGY. "
                "Tu parles comme un assistant naturel, chaleureux et competent, pas comme un formulaire. "
                "Tu peux repondre aux questions generales sur ton role, tes capacites ou la conversation. "
                "Avant de repondre, decide silencieusement si la question concerne vraiment le client charge. "
                "Utilise le contexte client uniquement si la question mentionne ou implique clairement le client, son score, son risque, "
                "ses paiements, son kit, son eligibilite, sa confiance ou une action operationnelle sur ce dossier. "
                "Si la question est generale, par exemple 'tu es qui ?', 'que peux-tu faire ?', 'pourquoi tu es la ?', "
                "ou une variante avec fautes comme 'que pex tu faire ?', reponds directement a cette question sans parler du score, "
                "du risque, de la probabilite de defaut ni du client charge. "
                "Tu comprends les fautes de frappe et les formulations orales. "
                "Ta reponse doit etre naturelle, amicale, utile et facile a lire. "
                "Tu dois t'appuyer uniquement sur les donnees fournies. "
                "Ne donne pas une decision de credit definitive; formule une recommandation operationnelle prudente. "
                "Evite les longues enumerations et le style rapport administratif. "
                "Reponds en 4 a 6 courts paragraphes, avec au maximum 3 puces si elles aident vraiment. "
                "Vise 180 a 250 mots. "
                "Pour une analyse client, commence par une phrase directe du type: 'Mon avis: ...'. "
                "Pour une question generale, commence naturellement sans dire 'Mon avis'. "
                "Explique pourquoi avec des mots simples, puis termine par l'action recommandee et une limite importante."
            ),
            input=(
                f"Question utilisateur: {question}\n\n"
                f"Contexte scoring client JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
            ),
            store=False,
        )
        answer = response.output_text.strip()
        if not answer:
            raise RuntimeError("OpenAI a retourne une reponse vide.")
        return {"provider": "openai", "answer": answer, "context": context}

    def _answer_locally(
        self,
        question: str,
        scoring_result: dict[str, Any],
        external_payload: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._compact_context(scoring_result, external_payload)
        score = scoring_result["score"]
        risk_level = scoring_result["risk_level"]
        probability = scoring_result["default_probability_90d"]
        client = context["client"]
        subscription = context["subscription"]
        features = context["features"]

        points_favorables: list[str] = []
        points_vigilance: list[str] = []

        if features["payment_success_rate"] >= 0.8:
            points_favorables.append("Le taux de paiement reussi est bon.")
        else:
            points_vigilance.append("Le taux de paiement reussi est faible ou instable.")

        if subscription["status"] == "active":
            points_favorables.append("Le kit est actuellement actif.")
        else:
            points_vigilance.append("Le kit est suspendu, ce qui est un signal de risque fort.")

        if features["orange_money_account_age_months"] >= 12:
            points_favorables.append("Le compte Orange Money a une anciennete rassurante.")
        else:
            points_vigilance.append("Le compte Orange Money est encore recent.")

        if features["income_to_fee_ratio"] >= 10:
            points_favorables.append("Le ratio revenu estime / abonnement laisse une marge de paiement correcte.")
        else:
            points_vigilance.append("La charge d'abonnement semble lourde par rapport au revenu estime.")

        if features["historical_risk_score"] >= 0.55:
            points_vigilance.append("Le risque historique fourni par la source externe est eleve.")
        else:
            points_favorables.append("Le risque historique externe est relativement contenu.")

        action = "Accepter avec suivi standard."
        if risk_level == "medium":
            action = "Accepter prudemment avec suivi rapproche des prochains paiements."
        elif risk_level == "high":
            action = "Declencher une revue humaine avant toute decision commerciale engageante."

        answer = f"""Conclusion
Pour {client['name']}, le modele donne un score de {score}/100. Le niveau de risque est {risk_level}, avec une probabilite estimee de defaut ou suspension a 90 jours de {probability}.

Pourquoi ce resultat
Le score combine le profil client, l'anciennete Orange Money, le revenu estime, le statut du kit, le nombre de mois payes et l'historique des paiements. La question posee etait: "{question}". D'apres les donnees disponibles, l'analyse principale est que le risque est tire par les signaux suivants: {', '.join(scoring_result['main_factors'])}.

Points de vigilance
{self._format_items(points_vigilance)}

Points favorables
{self._format_items(points_favorables)}

Action recommandee
{action}

Limites
Ce score vient d'un modele entraine sur donnees synthetiques. Il doit servir d'aide a la decision, pas de verdict automatique. Pour une decision reelle, il faut verifier les paiements recents, le statut terrain du kit et l'identite du client."""

        return {"provider": "local", "answer": answer, "context": context}

    def _compact_context(self, scoring_result: dict[str, Any], external_payload: dict[str, Any]) -> dict[str, Any]:
        data = external_payload.get("data", external_payload)
        client = data.get("client", {})
        subscription = data.get("subscription", {})
        return {
            "client": {
                "name": scoring_result.get("client_name") or "Client inconnu",
                "phone": scoring_result.get("phone"),
                "account_number": scoring_result.get("account_number"),
                "profession": client.get("profession"),
                "estimated_income_usd": client.get("estimatedIncomeUSD"),
                "orange_money_account_age_months": client.get("orangeMoneyAccountAgeMonths"),
                "historical_risk_score": client.get("historicalRiskScore"),
            },
            "subscription": {
                "kit_id": subscription.get("kitId"),
                "offer_name": subscription.get("offerName"),
                "status": subscription.get("status"),
                "paid_months_count": subscription.get("paidMonthsCount"),
            },
            "score": {
                "score": scoring_result["score"],
                "risk_level": scoring_result["risk_level"],
                "default_probability_90d": scoring_result["default_probability_90d"],
                "decision": scoring_result["decision"],
                "main_factors": scoring_result["main_factors"],
                "guardrails": scoring_result.get("guardrails", []),
                "model": scoring_result["model"],
            },
            "features": scoring_result.get("explanation", {}).get("features", scoring_result.get("features", {}))
            or self._features_from_scoring_result(scoring_result),
        }

    def _features_from_scoring_result(self, scoring_result: dict[str, Any]) -> dict[str, Any]:
        explanation = scoring_result.get("explanation", {})
        return explanation.get("features", {}) if isinstance(explanation, dict) else {}

    def _format_items(self, items: list[str]) -> str:
        if not items:
            return "- Aucun signal important dans cette categorie avec les donnees disponibles."
        return "\n".join(f"- {item}" for item in items)

    def _llm_safe_context(self, scoring_result: dict[str, Any]) -> dict[str, Any]:
        features = scoring_result.get("features", {})
        return {
            "client": {
                "identifier": "client_anonymise",
                "profession_risk_band": self._band(features.get("profession_risk_score", 0.5), 0.3, 0.6),
                "income_to_fee_band": self._band(features.get("income_to_fee_ratio", 0), 8, 15),
                "orange_money_age_band": self._band(features.get("orange_money_account_age_months", 0), 6, 18),
            },
            "subscription": {
                "kit_status": scoring_result.get("subscription", {}).get("status"),
                "paid_months_count": scoring_result.get("subscription", {}).get("paid_months_count"),
            },
            "score": {
                "score": scoring_result["score"],
                "risk_level": scoring_result["risk_level"],
                "default_probability_90d": scoring_result["default_probability_90d"],
                "decision": scoring_result["decision"],
                "main_factors": scoring_result["main_factors"],
                "guardrails": scoring_result.get("guardrails", []),
                "model_version": scoring_result["model"]["version"],
                "trained_on_synthetic_data": scoring_result["model"]["trained_on_synthetic_data"],
            },
            "payment_signals": {
                "payment_success_rate_band": self._band(features.get("payment_success_rate", 0), 0.5, 0.8),
                "failed_payment_count_12m": features.get("failed_payment_count_12m"),
                "late_payment_count_12m": features.get("late_payment_count_12m"),
                "missed_payment_count_12m": features.get("missed_payment_count_12m"),
                "days_since_last_payment_band": self._band(features.get("days_since_last_payment", 365), 30, 60),
            },
        }

    def _band(self, value: float, low_threshold: float, high_threshold: float) -> str:
        if value < low_threshold:
            return "low"
        if value < high_threshold:
            return "medium"
        return "high"
