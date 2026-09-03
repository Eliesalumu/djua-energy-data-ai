from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.solar_advisor.service import SolarAdvisorService


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_float(prompt: str, default: float | None = None) -> float | None:
    raw = ask(prompt, str(default) if default is not None else None)
    if raw == "":
        return None
    return float(raw.replace(",", "."))


def ask_int(prompt: str, default: int = 1) -> int:
    raw = ask(prompt, str(default))
    return max(1, int(raw))


def manual_flow() -> dict:
    print("")
    print("CONFIGURATEUR MANUEL")
    print("--------------------")
    payload = {
        "customer_id": ask("Identifiant client ou nom court", "client-demo"),
        "city": ask("Ville", "kinshasa").lower(),
        "housing_type": ask("Type de logement/activite", "menage urbain"),
        "people_count": ask_int("Nombre de personnes", 5),
        "autonomy_hours": ask_float("Autonomie souhaitee en heures", 10),
        "budget": ask_float("Budget approximatif XAF, laisser vide si inconnu", None),
        "preference": ask("Preference: economy, balanced, performance, autonomy", "balanced"),
        "source": "manual_cli",
        "appliances": [],
    }
    print("")
    print("Ajoute les appareils un par un. Exemples: television, congelateur, ampoule, ventilateur, telephone.")
    while True:
        name = ask("Nom de l'appareil, ou ENTER pour terminer")
        if not name:
            break
        quantity = ask_int("Quantite", 1)
        hours = ask_float("Heures d'utilisation par jour", None)
        power = ask_float("Puissance en W si connue, sinon ENTER", None)
        period = ask("Periode: day, night, mixed, continuous", "mixed")
        essential = ask("Indispensable ? oui/non", "oui").lower().startswith("o")
        item = {
            "name": name,
            "quantity": quantity,
            "hours_per_day": hours,
            "power_w": power,
            "usage_period": period,
            "essential": essential,
        }
        payload["appliances"].append({key: value for key, value in item.items() if value is not None})
    return payload


def conversation_flow(service: SolarAdvisorService) -> dict:
    print("")
    print("ASSISTANT CONVERSATIONNEL")
    print("-------------------------")
    print("Bonjour. Ici, le client peut parler simplement, sans connaitre le solaire.")
    print("L'assistant va le guider doucement et garder le contexte.")
    print("Exemple:")
    print("Je suis a Kinshasa, je veux alimenter 1 TV 5h, 1 congelateur 24h, 8 ampoules 6h, autonomie 10h.")
    print("Quand tu veux le devis, ecris: fais le devis")
    print("Commandes: /manuel pour saisir en formulaire, /quitter pour sortir.")
    context: dict = {"source": "conversation_cli"}
    while True:
        message = ask("Client")
        if message.lower() in {"/quitter", "quitter", "exit"}:
            raise SystemExit("Demo arretee.")
        if message.lower() in {"/manuel", "manuel"}:
            return manual_flow()
        step = service.conversation_step(message, context)
        context = step["request"]
        context["source"] = "conversation_cli"
        print("")
        print("Assistant:")
        print(step["assistant_message"])
        if step.get("warning") and not step.get("used_ai"):
            print(f"({step['warning']})")
        if step.get("next_questions") and not step.get("can_recommend") and not step.get("used_ai"):
            print("")
            print("Informations utiles a ajouter:")
            for question in step["next_questions"]:
                print(f"- {question}")
        if step.get("can_recommend"):
            request = step["request"]
            if not request.get("customer_id"):
                request["customer_id"] = "client-conversation"
            return request
        print("")


def print_recommendation(result: dict) -> None:
    print("")
    print("RESULTAT DE LA RECOMMANDATION")
    print("=============================")
    print(f"Recommendation : {result['recommendation_id']}")
    print(f"Consommation   : {result['consumption']['total_daily_energy_kwh']} kWh/jour")
    print(
        "Configuration  : "
        f"{result['sizing']['panel_count']} panneau(x) x {result['sizing']['panel_power_w']} W, "
        f"{result['sizing']['battery_count']} batterie(s), "
        f"onduleur {result['sizing']['inverter_power_w']} W"
    )
    print(f"Autonomie      : {result['sizing']['autonomy_hours_estimated']} h estimees")
    print(f"Devis demo     : {result['quote']['total_estimated']} {result['quote']['currency']}")
    if result["missing_information"]:
        print(f"Infos a confirmer : {', '.join(result['missing_information'])}")
    print("")
    print("Calcul appareil par appareil")
    for item in result["consumption"]["appliances"]:
        print(
            f"- {item['quantity']} x {item['name']} | {item['power_w']} W | "
            f"{item['hours_per_day']} h/j | {item['daily_energy_wh']} Wh/j"
        )
    print("")
    print("Explication technique courte")
    for item in result["explanation"]:
        print(f"- {item}")


def print_conversation_quote(service: SolarAdvisorService, result: dict) -> None:
    presentation = service.present_quote_with_ai(result)
    print("")
    print("Assistant:")
    print(presentation["message"])
    if presentation.get("warning") and not presentation.get("used_ai"):
        print(f"({presentation['warning']})")
    details = ask("Afficher le detail technique brut ? oui/non", "non").lower()
    if details.startswith("o"):
        print_recommendation(result)


def maybe_ai_explanation(service: SolarAdvisorService, recommendation_id: str) -> None:
    choice = ask("Voulez-vous une explication reformulee par l'IA ? oui/non", "oui").lower()
    if not choice.startswith("o"):
        return
    explanation = service.explain_with_ai(recommendation_id)
    print("")
    print("EXPLICATION IA")
    print("--------------")
    print(explanation["explanation"])
    print("")
    print(f"IA utilisee: {explanation['used_ai']} | modele: {explanation['model']} | note: {explanation['warning']}")


def maybe_contact(service: SolarAdvisorService, recommendation_id: str) -> None:
    choice = ask("Creer une demande de contact Orange Energy ? oui/non", "oui").lower()
    if not choice.startswith("o"):
        return
    contact = {
        "name": ask("Nom du client", "Client demo"),
        "phone": ask("Telephone", "+242000000000"),
        "email": ask("Email, optionnel"),
        "message": ask("Message", "Demande de rappel Orange Energy."),
    }
    saved = service.create_contact_request(recommendation_id, contact)
    print("")
    print("Demande contact creee")
    print(json.dumps(saved, indent=2, ensure_ascii=False))


def main() -> None:
    service = SolarAdvisorService()
    print("DJUA AI Solar Advisor - Demo interactive")
    print("========================================")
    print("1. Assistant conversationnel guide")
    print("2. Configurateur manuel")
    mode = ask("Choisis le parcours", "1")
    payload = conversation_flow(service) if mode == "1" else manual_flow()
    result = service.recommend(payload)
    if mode == "1":
        print_conversation_quote(service, result)
    else:
        print_recommendation(result)
    maybe_ai_explanation(service, result["recommendation_id"])
    maybe_contact(service, result["recommendation_id"])
    print("")
    print("Resultat API equivalent : GET /solar-advisor/recommendations/" + result["recommendation_id"])


if __name__ == "__main__":
    main()
