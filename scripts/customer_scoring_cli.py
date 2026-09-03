from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from djua_energy.scoring.demo_scenarios import SCENARIOS
from djua_energy.scoring.service import CustomerScoringService


def _print_human(result: dict[str, Any]) -> None:
    print("")
    print("DJUA ENERGY - RESULTAT SCORING CLIENT")
    print("=====================================")
    print(f"Client        : {result.get('client_name') or 'N/A'}")
    print(f"Compte        : {result.get('account_number') or 'N/A'}")
    print(f"Telephone     : {result.get('phone') or 'N/A'}")
    print(f"Kit           : {result['subscription'].get('kit_id') or 'N/A'}")
    print(f"Offre         : {result['subscription'].get('offer_name') or 'N/A'}")
    print(f"Statut kit    : {result['subscription'].get('status') or 'N/A'}")
    print("")
    print(f"Score         : {result['score']}/100")
    print(f"Niveau risque : {result['risk_level']}")
    print(f"Defaut 90j    : {result['default_probability_90d']}")
    print(f"Decision      : {result['decision']}")
    print(f"Modele        : {result['model']['version']}")
    print("")
    print("Facteurs principaux:")
    for factor in result["main_factors"]:
        print(f" - {factor}")
    if result.get("guardrails"):
        print("")
        print("Garde-fous appliques:")
        for guardrail in result["guardrails"]:
            print(f" - {guardrail}")
    print("")
    print("Explication:")
    print(result["explanation"]["summary"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo CLI du scoring client DJUA ENERGY.")
    parser.add_argument("--phone", default="", help="Numero Orange Money a scorer via l'API externe configuree.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="bon", help="Scenario local si --phone est absent.")
    parser.add_argument("--llm", action="store_true", help="Demande une explication OpenAI si OPENAI_API_KEY est configuree.")
    parser.add_argument("--json", action="store_true", help="Affiche la reponse JSON complete.")
    args = parser.parse_args()

    service = CustomerScoringService()
    if args.phone:
        result = service.score_from_external_api(args.phone, explain_with_llm=args.llm)
    else:
        result = service.score_payload(SCENARIOS[args.scenario], explain_with_llm=args.llm)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
