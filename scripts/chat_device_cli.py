from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.chat.service import DjuaChatService


class _NoLlmClient:
    available = False
    disabled_by_user = True


def _build_service(no_llm: bool) -> DjuaChatService:
    if no_llm:
        return DjuaChatService(llm_client=_NoLlmClient())
    return DjuaChatService()


def _print_result(result, require_llm: bool) -> None:
    if require_llm and not result.used_llm:
        raise SystemExit(f"OpenAI requis mais fallback local utilise: {result.error}")

    source = "openai" if result.used_llm else "local"
    print("")
    print(f"IA DJUA PARC - source: {source}")
    print("=========================")
    print(result.answer)
    print("")
    print(f"Intent  : {result.intent}")
    if result.device_id:
        print(f"Device  : {result.device_id}")
    print(f"Sources : {', '.join(result.sources)}")
    if result.error and "OPENAI_API_KEY absente" not in result.error:
        print(f"Note    : {result.error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat IA pour la surveillance du parc DJUA ENERGY.")
    parser.add_argument("--question", default="", help="Question directe. Si absent, mode interactif.")
    parser.add_argument("--no-llm", action="store_true", help="Force le fallback local sans OpenAI.")
    parser.add_argument("--require-llm", action="store_true", help="Echoue si OpenAI ne repond pas.")
    args = parser.parse_args()

    print("Djua Energy - Copilote IA conversationnel")
    print("=========================================")
    print("Surveillance du parc, devices, alertes et priorites terrain.")
    print(f"OpenAI detecte : {'oui' if os.getenv('OPENAI_API_KEY') else 'non'}")
    print(f"Mode LLM       : {'desactive' if args.no_llm else 'active si disponible'}")
    print("")
    print("Exemples :")
    print("- Résume-moi l'état du parc")
    print("- Quels devices sont critiques ?")
    print("- Parle-moi du device-3")
    print("- Que dois-je traiter en priorité aujourd'hui ?")
    print("")
    service = _build_service(args.no_llm)

    if args.question:
        result = service.answer(args.question)
        _print_result(result, args.require_llm)
        return

    while True:
        message = input("\nVous : ").strip()
        if message.lower() in {"q", "quit", "exit"}:
            break
        if not message:
            continue
        result = service.answer(message)
        _print_result(result, args.require_llm)

    print("\nFin du chat.")


if __name__ == "__main__":
    main()
