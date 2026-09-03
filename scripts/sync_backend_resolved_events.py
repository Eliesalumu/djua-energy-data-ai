from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lance le flux pull: API IA/Data -> backend metier -> prediction -> ACK."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="URL de l'API IA/Data locale.")
    parser.add_argument("--backend-url", required=True, help="URL du backend metier a consommer.")
    parser.add_argument("--cursor", default=None, help="Curseur de pagination backend.")
    parser.add_argument("--limit", type=int, default=100, help="Nombre maximum de snapshots a traiter.")
    parser.add_argument("--no-ack", action="store_true", help="Traiter sans envoyer d'ACK au backend.")
    args = parser.parse_args()

    endpoint = f"{args.api_url.rstrip('/')}/v1/backend-sync/resolved-telemetry-events/run"
    payload = {
        "backend_base_url": args.backend_url,
        "cursor": args.cursor,
        "limit": args.limit,
        "ack": not args.no_ack,
    }

    print("SYNC BACKEND -> IA/DATA")
    print("=======================")
    print("Endpoint IA/Data:")
    print(endpoint)
    print("Payload de synchronisation:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    try:
        result = post_json(endpoint, payload)
    except HTTPError as exc:
        print(f"\nErreur API IA/Data: HTTP {exc.code}")
        print(exc.read().decode("utf-8", errors="replace"))
        raise SystemExit(1) from exc
    except URLError as exc:
        print("\nImpossible de joindre l'API IA/Data.")
        print("Demarrez-la avec:")
        print(".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000")
        print(f"Detail: {exc.reason}")
        raise SystemExit(1) from exc

    print("\nResultat:")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
