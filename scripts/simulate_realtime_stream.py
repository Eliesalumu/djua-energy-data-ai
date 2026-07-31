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
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _scenario_for_cycle(cycle: int, cycles: int) -> str:
    if cycle < max(1, cycles // 3):
        return "normal_operation"
    if cycle < max(2, (cycles * 2) // 3):
        return "progressive_battery_degradation"
    return "battery_overheating"


def _record_for_cycle(cycle: int, cycles: int, interval_seconds: int, seed: int, run_id: str) -> dict:
    scenario = _scenario_for_cycle(cycle, cycles)
    generator = SyntheticTelemetryGenerator(seed=seed + cycle, num_kits=1)
    records = generator.generate(scenarios=[scenario], duration_hours=max(1, (cycle // 2) + 1))
    record = records[min(cycle, len(records) - 1)]
    base_time = 1700000000 + cycle * interval_seconds
    record["event_time"] = str(base_time)
    record["ingestion_time"] = str(base_time + 10)
    record["last_successful_sync_at"] = str(base_time)
    record["message_id"] = f"realtime-{run_id}-device-0-{cycle:04d}"
    record["sequence_number"] = cycle + 1
    record["sampling_interval_seconds"] = interval_seconds
    record.pop("scenario", None)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Simule un flux device vers POST /telemetry/analyze")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="URL de base de l'API locale")
    parser.add_argument("--cycles", type=int, default=18, help="Nombre de mesures a envoyer")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Intervalle simule entre deux mesures")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pause reelle entre deux envois")
    parser.add_argument("--seed", type=int, default=91, help="Graine de simulation")
    args = parser.parse_args()

    endpoint = f"{args.api_url.rstrip('/')}/telemetry/analyze"
    print("Djua Energy - Simulation temps reel")
    print("===================================")
    print(f"Endpoint          : {endpoint}")
    print(f"Mesures envoyees  : {args.cycles}")
    print(f"Intervalle simule : {args.interval_seconds} secondes")
    print(f"Pause reelle      : {args.sleep_seconds} secondes")
    print("")

    run_id = str(int(time.time()))
    for cycle in range(args.cycles):
        record = _record_for_cycle(cycle, args.cycles, args.interval_seconds, args.seed, run_id)
        try:
            result = post_json(endpoint, {"records": [record]})
        except URLError as exc:
            print("\nImpossible de joindre l'API locale.")
            print("Demarrez-la avec :")
            print(".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload")
            raise SystemExit(1) from exc

        alert = result.get("alert") or {}
        stored = result.get("stored_prediction") or {}
        if result.get("status") != "processed":
            print(
                f"[{cycle + 1:02d}/{args.cycles}] "
                f"{record['device_id']} ignore: {result.get('status')} "
                f"doublons={result.get('duplicate_records', 0)}"
            )
        else:
            print(
                f"[{cycle + 1:02d}/{args.cycles}] "
                f"{record['device_id']} "
                f"temp_batt={record['battery_temperature_c']}C "
                f"voltage={record['battery_voltage_v']}V "
                f"charge={record['state_of_charge_pct']}% "
                f"connexion={record.get('connection_status')} "
                f"score_ia={stored.get('risk_score', 'n/a')} "
                f"risque={stored.get('risk_level', alert.get('priority'))} "
                f"fenetre={result.get('prediction_window_records')} "
                f"action={stored.get('recommended_action') or alert.get('recommended_action')}"
            )
        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    print("\nEtat courant consultable avec :")
    print(f"Invoke-RestMethod {args.api_url.rstrip('/')}/realtime/devices/device-0/state")
    print(f"Invoke-RestMethod {args.api_url.rstrip('/')}/realtime/devices/device-0/predictions")


if __name__ == "__main__":
    main()
