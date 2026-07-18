from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import URLError
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo API for POST /telemetry/analyze")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Base URL of the local API")
    parser.add_argument("--scenario", default="movement_then_connectivity_loss", help="Synthetic scenario to send")
    parser.add_argument("--records", type=int, default=6, help="Number of records to send")
    parser.add_argument("--seed", type=int, default=None, help="Synthetic generator seed")
    args = parser.parse_args()

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
