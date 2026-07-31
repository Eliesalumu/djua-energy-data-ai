from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _print_frontend_contract(api_url: str) -> None:
    base_url = api_url.rstrip("/")
    endpoints = [
        "/frontend/command-center",
        "/frontend/fleet",
        "/frontend/decisions/decision-001",
        "/frontend/kits/kit-0/digital-twin",
        "/frontend/customers/client-001/risk-profile",
        "/frontend/performance",
        "/frontend/admin/data-ai",
        "/frontend/realtime/events",
    ]

    print("Djua Energy - Test CLI contrat frontend")
    print("=======================================")
    print(f"API : {base_url}")

    failures = 0
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            payload = get_json(url)
        except (HTTPError, URLError) as exc:
            failures += 1
            print(f"[KO] {endpoint} -> {exc}")
            continue
        meta = payload.get("meta", {})
        keys = ", ".join(sorted(payload.keys())[:6])
        print(f"[OK] {endpoint}")
        print(f"     schema={meta.get('schema_version', 'n/a')} mode={meta.get('data_mode', meta.get('transport', 'n/a'))} keys={keys}")
        if meta.get("ai_traceability"):
            print(f"     ai={meta['ai_traceability']}")
        if meta.get("model_runs"):
            print(f"     model_runs={len(meta['model_runs'])}")

    if failures:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo API for POST /telemetry/analyze")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Base URL of the local API")
    parser.add_argument("--scenario", default="movement_then_connectivity_loss", help="Synthetic scenario to send")
    parser.add_argument("--records", type=int, default=6, help="Number of records to send")
    parser.add_argument("--seed", type=int, default=None, help="Synthetic generator seed")
    parser.add_argument(
        "--frontend-contract",
        action="store_true",
        help="Teste les endpoints de demonstration destines a l'interface frontend.",
    )
    args = parser.parse_args()

    if args.frontend_contract:
        try:
            _print_frontend_contract(args.api_url)
        except URLError as exc:
            print("\nImpossible de joindre l'API locale.")
            print("Demarrez-la avec :")
            print(".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload")
            raise SystemExit(1) from exc
        return

    seed = args.seed if args.seed is not None else int(time.time())
    generator = SyntheticTelemetryGenerator(seed=seed, num_kits=1)
    generated = generator.generate(scenarios=[args.scenario], duration_hours=max(1, args.records // 2))
    records = generated[: args.records]

    endpoint = f"{args.api_url.rstrip('/')}/telemetry/analyze"

    print("Djua Energy - Demo API telemetry/analyze")
    print("========================================")
    print(f"Endpoint : {endpoint}")
    print(f"Scenario : {args.scenario}")
    print(f"Records  : {len(records)}")

    try:
        result = post_json(endpoint, {"records": records})
    except URLError as exc:
        print("\nImpossible de joindre l'API locale.")
        print("Demarrez-la avec :")
        print(".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload")
        raise SystemExit(1) from exc

    alert = result.get("alert") or {}
    print("\nResultat")
    print("--------")
    print(f"Status              : {result.get('status')}")
    print(f"Device              : {result.get('device_id')}")
    print(f"Records analyzed    : {result.get('records_analyzed')}")
    print(f"Quarantined records : {result.get('quarantined_records')}")
    print(f"Duplicate records   : {result.get('duplicate_records')}")
    print(f"Alert priority      : {alert.get('priority')}")
    print(f"Maintenance priority: {alert.get('maintenance_priority')}")
    print(f"Security priority   : {alert.get('security_priority')}")
    print(f"Recommended action  : {alert.get('recommended_action')}")


if __name__ == "__main__":
    main()
