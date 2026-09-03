from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from djua_energy.scoring.conversation import CustomerRiskConversationService
from djua_energy.scoring.demo_scenarios import SCENARIOS
from djua_energy.scoring.service import CustomerScoringService


def _resolve_payload(args: argparse.Namespace) -> tuple[dict, dict]:
    scoring_service = CustomerScoringService()
    if args.phone:
        if args.external_api_base_url:
            os.environ["DJUA_EXTERNAL_API_BASE_URL"] = args.external_api_base_url.rstrip("/")
        payload = scoring_service.external_api_client.get_scoring_data(args.phone)
        scoring = scoring_service.score_payload(payload, explain_with_llm=False)
        return payload, scoring
    payload = SCENARIOS[args.scenario]
    scoring = scoring_service.score_payload(payload, explain_with_llm=False)
    return payload, scoring


def _print_context(scoring: dict) -> None:
    print("")
    print("Contexte client charge")
    print("======================")
    print(f"Client        : {scoring.get('client_name')}")
    print(f"Telephone     : {scoring.get('phone')}")
    print(f"Score ML      : {scoring['score']}/100")
    print(f"Risque        : {scoring['risk_level']}")
    print(f"Defaut 90j    : {scoring['default_probability_90d']}")
    print("")


def _ask_once(question: str, payload: dict, scoring: dict, use_llm: bool, require_llm: bool) -> None:
    chat = CustomerRiskConversationService()
    result = chat.answer(question, scoring, payload, use_llm=use_llm, require_llm=require_llm)
    print("")
    print(f"IA DJUA - source: {result['provider']}")
    print("========================")
    print(result["answer"])
    if result.get("warning"):
        print("")
        print(f"Note: {result['warning']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat conversationnel autour du scoring client DJUA ENERGY.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="moyen", help="Client demo local.")
    parser.add_argument("--phone", default="", help="Numero Orange Money pour interroger l'API externe.")
    parser.add_argument("--external-api-base-url", default="", help="Base URL de l'API externe deja en ligne.")
    parser.add_argument("--question", default="", help="Question a poser a l'IA. Si absent, mode interactif.")
    parser.add_argument("--llm", action="store_true", default=None, help="Utilise OpenAI si OPENAI_API_KEY est configuree.")
    parser.add_argument("--no-llm", action="store_true", help="Force la reponse locale sans OpenAI.")
    parser.add_argument("--require-llm", action="store_true", help="Echoue clairement si OpenAI ne repond pas.")
    args = parser.parse_args()

    use_llm = bool(os.getenv("OPENAI_API_KEY")) if args.llm is None else args.llm
    if args.no_llm:
        use_llm = False

    payload, scoring = _resolve_payload(args)
    _print_context(scoring)
    print(f"OpenAI detecte : {'oui' if os.getenv('OPENAI_API_KEY') else 'non'}")
    print(f"Mode LLM       : {'active' if use_llm else 'desactive'}")

    if args.question:
        _ask_once(args.question, payload, scoring, use_llm=use_llm, require_llm=args.require_llm)
        return

    print("Pose une question. Exemples:")
    print("- IA, que penses-tu de ce client ?")
    print("- Pourquoi son score est-il moyen ?")
    print("- Est-ce qu'on peut lui faire confiance ?")
    print("- Quelle action recommandes-tu ?")
    print("")
    print("Tape 'exit' pour sortir.")
    while True:
        question = input("\nVous > ").strip()
        if question.lower() in {"exit", "quit", "q"}:
            break
        if not question:
            continue
        _ask_once(question, payload, scoring, use_llm=use_llm, require_llm=args.require_llm)


if __name__ == "__main__":
    main()
