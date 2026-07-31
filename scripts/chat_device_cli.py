from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.chat.service import DjuaChatService


def main() -> None:
    print("Djua Energy - Copilote IA conversationnel")
    print("=========================================")
    print("Exemples : parle-moi du device-4 | quel device est normal ? | q")
    service = DjuaChatService()

    while True:
        message = input("\nVous : ").strip()
        if message.lower() in {"q", "quit", "exit"}:
            break
        if not message:
            continue
        result = service.answer(message)
        print("\nIA : " + result.answer)
        mode = "OpenAI" if result.used_llm else "local"
        print(f"\nMode : {mode} | Sources : {', '.join(result.sources)}")
        if result.error:
            print(f"Note : {result.error}")

    print("\nFin du chat.")


if __name__ == "__main__":
    main()
