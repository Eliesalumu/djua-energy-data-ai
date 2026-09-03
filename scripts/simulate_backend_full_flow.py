from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator


def _demo_ids(run_id: str, *, fixed: bool) -> dict[str, str]:
    suffix = "001" if fixed else run_id[-6:]
    return {
        "client_id": f"client-sim-{suffix}",
        "kit_id": f"kit-sim-{suffix}",
        "device_id": f"device-sim-{suffix}",
        "contract_id": f"contract-sim-{suffix}",
        "assignment_id": f"assignment-sim-{suffix}",
        "installation_id": f"installation-sim-{suffix}",
    }


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _scenario_for_tick(tick: int, ticks: int) -> str:
    if tick < max(1, ticks // 3):
        return "normal_operation"
    if tick < max(2, (ticks * 2) // 3):
        return "progressive_battery_degradation"
    return "battery_overheating"


def _payment_history(as_of: datetime, ids: dict[str, str], *, profile: str) -> list[dict]:
    payments: list[dict] = []
    for month_offset in range(6, 0, -1):
        due_date = as_of - timedelta(days=month_offset * 30)
        paid_delay_days = 0
        status = "paid"
        if profile == "late" and month_offset in {2, 4}:
            paid_delay_days = 7 if month_offset == 4 else 14
            status = "late"
        payments.append(
            {
                "payment_id": f"pay-sim-{month_offset:02d}",
                "client_id": ids["client_id"],
                "contract_id": ids["contract_id"],
                "due_date": due_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "paid_at": (due_date + timedelta(days=paid_delay_days)).replace(
                    hour=10,
                    minute=0,
                    second=0,
                    microsecond=0,
                ).isoformat(),
                "amount_due": 20,
                "amount_paid": 20,
                "status": status,
                "method": "orange_money",
            }
        )
    return payments


def _record_for_tick(
    tick: int,
    ticks: int,
    base_timestamp: int,
    interval_seconds: int,
    run_id: str,
    ids: dict[str, str],
) -> dict:
    scenario = _scenario_for_tick(tick, ticks)
    generator = SyntheticTelemetryGenerator(seed=700 + tick, num_kits=1)
    records = generator.generate(scenarios=[scenario], duration_hours=max(1, tick + 1))
    record = records[min(tick, len(records) - 1)]
    event_time = base_timestamp + tick * interval_seconds
    if scenario == "normal_operation":
        record["battery_error_code"] = "NONE"
        record["solar_error_code"] = "NONE"
        record["connection_status"] = "connected"
        record["network_quality"] = "good"
        record["connectivity_gap_seconds"] = 0
        record["device_error_code"] = "NONE"
        record["abnormal_consumption_detected"] = False
        record["sensor_failure_detected"] = False
    if scenario == "progressive_battery_degradation":
        record["battery_voltage_v"] = round(float(record["battery_voltage_v"]) - tick * 0.12, 2)
        record["state_of_health_pct"] = round(max(72, float(record["state_of_health_pct"]) - tick * 2.5), 2)
    if scenario == "battery_overheating":
        record["battery_temperature_c"] = round(max(float(record["battery_temperature_c"]), 51 + tick * 0.8), 2)
        record["device_temperature_c"] = round(record["battery_temperature_c"] + 2.5, 2)
        record["state_of_health_pct"] = round(max(62, float(record["state_of_health_pct"]) - tick * 3.5), 2)
        record["battery_error_code"] = "BATT_TEMP_HIGH"
        record["abnormal_consumption_detected"] = True
    record.update(
        {
            "message_id": f"backend-sim-{run_id}-{tick:04d}",
            "device_id": ids["device_id"],
            "kit_id": ids["kit_id"],
            "serial_number": "SN-SIM-001",
            "event_time": str(event_time),
            "sequence_number": tick + 1,
            "scenario": scenario,
        }
    )
    return record


def _payload_for_tick(
    tick: int,
    ticks: int,
    base_timestamp: int,
    interval_seconds: int,
    run_id: str,
    ids: dict[str, str],
    payment_profile: str,
) -> dict:
    as_of = datetime.fromtimestamp(base_timestamp + tick * interval_seconds + 60, tz=UTC)
    return {
        "schema_version": "1.0",
        "request_id": f"req-backend-sim-{run_id}-{tick:04d}",
        "as_of": as_of.isoformat(),
        "identity": {
            "client_id": ids["client_id"],
            "kit_id": ids["kit_id"],
            "device_id": ids["device_id"],
            "contract_id": ids["contract_id"],
            "assignment_id": ids["assignment_id"],
            "installation_id": ids["installation_id"],
            "resolution_status": "resolved",
        },
        "customer": {
            "customer_segment": "residential",
            "tenure_months": 18,
            "active_contracts": 1,
        },
        "contract": {
            "status": "active",
            "periodic_amount_usd": 20,
        },
        "assignment": {
            "assignment_id": ids["assignment_id"],
            "client_id": ids["client_id"],
            "kit_id": ids["kit_id"],
            "device_id": ids["device_id"],
            "status": "active",
        },
        "payments": _payment_history(as_of, ids, profile=payment_profile),
        "context": {
            "region": "kinshasa",
            "season": "dry",
            "day_period": "day",
            "ambient_temperature_c": 34,
        },
        "records": [_record_for_tick(tick, ticks, base_timestamp, interval_seconds, run_id, ids)],
        "data_quality": {
            "identity_resolved": True,
            "missing_features": [],
            "warnings": [],
        },
    }


def _safe_call(label: str, func, url: str, payload: dict | None = None) -> dict:
    try:
        return func(url) if payload is None else func(url, payload)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"\n{label} a echoue: HTTP {exc.code}")
        print(detail)
        raise SystemExit(1) from exc
    except URLError as exc:
        print("\nImpossible de joindre l'API locale.")
        print("Demarrez-la dans un autre PowerShell avec :")
        print(".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000")
        raise SystemExit(1) from exc


def _risk_label(score: int | float | None) -> str:
    if score is None:
        return "inconnu"
    value = float(score)
    if value >= 70:
        return "eleve"
    if value >= 40:
        return "moyen"
    return "faible"


def _scenario_sentence(scenario: str) -> str:
    labels = {
        "normal_operation": "les mesures ressemblent a un fonctionnement normal",
        "progressive_battery_degradation": "les mesures montrent une degradation progressive de la batterie",
        "battery_overheating": "les mesures montrent une surchauffe batterie",
    }
    return labels.get(scenario, f"scenario technique observe: {scenario}")


def _action_sentence(action: str | None) -> str:
    labels = {
        "monitor": "On continue la surveillance.",
        "payment_monitoring": "On surveille surtout le paiement.",
        "technical_intervention": "Il faut planifier une intervention technique.",
        "immediate_intervention": "Il faut intervenir rapidement.",
        "resolve_identity": "Il faut d'abord corriger le rattachement client-kit.",
        "fix_payload": "Il faut corriger les donnees envoyees.",
    }
    return labels.get(str(action or ""), f"Action recommandee: {action}.")


def _print_json_block(title: str, payload: dict) -> None:
    print(f"{title}:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _record_json_view(record: dict) -> dict:
    return {
        "identification_mesure": {
            "message_id": record.get("message_id"),
            "schema_version": record.get("schema_version"),
            "message_type": record.get("message_type"),
            "device_id": record.get("device_id"),
            "kit_id": record.get("kit_id"),
            "serial_number": record.get("serial_number"),
            "event_time": record.get("event_time"),
            "sequence_number": record.get("sequence_number"),
        },
        "batterie": {
            "battery_voltage_v": record.get("battery_voltage_v"),
            "battery_current_a": record.get("battery_current_a"),
            "battery_power_w": record.get("battery_power_w"),
            "battery_temperature_c": record.get("battery_temperature_c"),
            "state_of_charge_pct": record.get("state_of_charge_pct"),
            "state_of_health_pct": record.get("state_of_health_pct"),
            "charge_duration_seconds": record.get("charge_duration_seconds"),
            "discharge_duration_seconds": record.get("discharge_duration_seconds"),
            "battery_age_months": record.get("battery_age_months"),
            "battery_error_code": record.get("battery_error_code"),
        },
        "solaire": {
            "solar_voltage_v": record.get("solar_voltage_v"),
            "solar_current_a": record.get("solar_current_a"),
            "solar_power_w": record.get("solar_power_w"),
            "energy_generated_wh": record.get("energy_generated_wh"),
            "panel_temperature_c": record.get("panel_temperature_c"),
            "solar_irradiance_w_m2": record.get("solar_irradiance_w_m2"),
            "solar_error_code": record.get("solar_error_code"),
        },
        "consommation": {
            "load_voltage_v": record.get("load_voltage_v"),
            "load_current_a": record.get("load_current_a"),
            "load_power_w": record.get("load_power_w"),
            "energy_consumed_wh": record.get("energy_consumed_wh"),
            "overload_detected": record.get("overload_detected"),
            "short_circuit_detected": record.get("short_circuit_detected"),
            "abnormal_consumption_detected": record.get("abnormal_consumption_detected"),
        },
        "securite_et_position": {
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "gps_accuracy_m": record.get("gps_accuracy_m"),
            "distance_from_installation_m": record.get("distance_from_installation_m"),
            "geofence_status": record.get("geofence_status"),
            "speed_mps": record.get("speed_mps"),
            "movement_detected": record.get("movement_detected"),
            "movement_duration_seconds": record.get("movement_duration_seconds"),
            "movement_event_count": record.get("movement_event_count"),
            "tamper_detected": record.get("tamper_detected"),
            "enclosure_opened": record.get("enclosure_opened"),
            "impact_detected": record.get("impact_detected"),
            "identity_mismatch_detected": record.get("identity_mismatch_detected"),
        },
        "connectivite_et_boitier": {
            "connectivity_type": record.get("connectivity_type"),
            "connection_status": record.get("connection_status"),
            "connectivity_gap_seconds": record.get("connectivity_gap_seconds"),
            "network_operator": record.get("network_operator"),
            "network_quality": record.get("network_quality"),
            "device_temperature_c": record.get("device_temperature_c"),
            "reset_count": record.get("reset_count"),
            "missing_measurement_count": record.get("missing_measurement_count"),
            "sensor_failure_detected": record.get("sensor_failure_detected"),
            "device_error_code": record.get("device_error_code"),
        },
        "contexte": {
            "region": record.get("region"),
            "season": record.get("season"),
            "day_period": record.get("day_period"),
            "ambient_temperature_c": record.get("ambient_temperature_c"),
            "humidity_pct": record.get("humidity_pct"),
            "installation_type": record.get("installation_type"),
            "usage_profile": record.get("usage_profile"),
            "security_risk_zone": record.get("security_risk_zone"),
            "scenario_demo": record.get("scenario"),
        },
    }


def _backend_payload_json_view(payload: dict) -> dict:
    return {
        "qui_envoie": "backend_metier_simule",
        "a_qui": "api_ia_data",
        "identity": payload.get("identity"),
        "customer": payload.get("customer"),
        "contract": payload.get("contract"),
        "assignment": payload.get("assignment"),
        "payments_raw_count": len(payload.get("payments") or []),
        "records_count": len(payload.get("records") or []),
        "record": _record_json_view(payload["records"][0]),
    }


def _ia_result_json_view(payload: dict, result: dict) -> dict:
    scores = result.get("scores", {})
    decision = result.get("decision", {})
    trend = result.get("trend_source", {})
    persistence = result.get("persistence", {})
    data_quality = result.get("data_quality", {})
    identity = payload.get("identity", {})
    technical_risk = scores.get("operational_risk")
    payment_risk = scores.get("payment_risk")
    action = decision.get("recommended_action")
    return {
        "relation_client_kit": {
            "client_id": identity.get("client_id"),
            "kit_id": identity.get("kit_id"),
            "device_id": identity.get("device_id"),
            "contract_id": identity.get("contract_id"),
            "assignment_id": identity.get("assignment_id"),
            "source_verite": "backend_metier",
        },
        "historique_utilise": {
            "device_id": identity.get("device_id"),
            "prediction_window_records": trend.get("prediction_window_records"),
            "ce_que_l_ia_compare": [
                "tendance_temperature_batterie",
                "tendance_tension_batterie",
                "coupures_reseau",
                "mouvements_et_sabotage",
                "anomalies_consommation",
                "historique_paiements_raw",
            ],
        },
        "scores_calcules": {
            "technical_risk": {
                "score": technical_risk,
                "niveau": _risk_label(technical_risk),
            },
            "payment_risk": {
                "score": payment_risk,
                "niveau": _risk_label(payment_risk),
            },
            "client_value": scores.get("client_value"),
            "intervention_priority": scores.get("intervention_priority"),
        },
        "decision": {
            "recommended_action": action,
            "explication_simple": _action_sentence(action),
            "priority": decision.get("priority"),
            "confidence": decision.get("confidence"),
            "human_review_required": decision.get("human_review_required"),
        },
        "stockage_effectue": {
            "telemetry_records": "mesure brute rattachee au client/kit/device",
            "prediction_history": "prediction technique historisee",
            "device_state": "dernier etat courant du kit",
            "customer_decision_history": "decision client historisee",
            "customers": "derniere fiche client prete pour le frontend",
            "decision_id": persistence.get("decision_id"),
        },
        "data_quality": data_quality,
    }


def _print_tick_result(tick: int, ticks: int, payload: dict, result: dict, *, technical: bool) -> None:
    decision = result.get("decision", {})
    persistence = result.get("persistence", {})
    data_quality = result.get("data_quality", {})
    latest_record = payload["records"][0]
    scenario = str(latest_record.get("scenario"))

    print(f"\nMESURE {tick + 1}/{ticks}")
    _print_json_block("JSON recu du backend", _backend_payload_json_view(payload))
    print(
        "Interpretation IA : "
        f"d'apres cette mesure et l'historique, {_scenario_sentence(scenario)}."
    )
    _print_json_block("JSON produit par l'API IA/Data", _ia_result_json_view(payload, result))
    if decision.get("human_review_required"):
        print("Un humain doit verifier ou valider cette decision.")

    if technical:
        _print_json_block(
            "Details techniques",
            {
                "tables_alimentees": [
                    "telemetry_records",
                    "prediction_history",
                    "device_state",
                    "customer_decision_history",
                    "customers",
                ],
                "decision_id": persistence.get("decision_id"),
            },
        )
    if data_quality.get("warnings"):
        _print_json_block("Avertissements donnees", {"warnings": data_quality["warnings"]})


def _print_readback(api_url: str, ids: dict[str, str], *, technical: bool) -> None:
    base = api_url.rstrip("/")
    customer = _safe_call("Lecture customer", get_json, f"{base}/v1/customers/{ids['client_id']}")
    predictions_url = f"{base}/v1/predictions?{urlencode({'client_id': ids['client_id'], 'limit': 5})}"
    predictions = _safe_call("Lecture predictions", get_json, predictions_url)
    decisions_url = f"{base}/v1/customer/decisions?{urlencode({'client_id': ids['client_id'], 'limit': 5})}"
    decisions = _safe_call("Lecture decisions", get_json, decisions_url)
    state = _safe_call("Lecture device_state", get_json, f"{base}/realtime/devices/{ids['device_id']}/state")

    print("\nCE QUE VOIT LE FRONTEND")
    print("=======================")
    frontend_view = {
        "role_frontend": "lecture_des_resultats_deja_prepares",
        "customer_card": {
            "client_id": customer.get("client_id"),
            "latest_kit_id": customer.get("latest_kit_id"),
            "latest_device_id": customer.get("latest_device_id"),
            "latest_contract_id": customer.get("latest_contract_id"),
            "latest_assignment_id": customer.get("latest_assignment_id"),
            "latest_client_value_score": customer.get("latest_client_value_score"),
            "latest_payment_risk_score": customer.get("latest_payment_risk_score"),
            "latest_operational_risk_score": customer.get("latest_operational_risk_score"),
            "latest_intervention_priority_score": customer.get("latest_intervention_priority_score"),
            "latest_decision_id": customer.get("latest_decision_id"),
            "latest_decision_at": customer.get("latest_decision_at"),
        },
        "device_state": {
            "device_id": state.get("device_id"),
            "kit_id": state.get("kit_id"),
            "client_id": state.get("client_id"),
            "risk_score": state.get("risk_score"),
            "risk_level": state.get("risk_level"),
            "alert_priority": state.get("alert_priority"),
            "recommended_action": state.get("recommended_action"),
            "last_event_time": state.get("last_event_time"),
            "last_prediction_at": state.get("last_prediction_at"),
        },
        "last_prediction": None,
        "last_decision": None,
    }
    if decisions.get("items"):
        first_decision = decisions["items"][0]
        frontend_view["last_decision"] = {
            "decision_id": first_decision.get("decision_id"),
            "client_id": first_decision.get("client_id"),
            "kit_id": first_decision.get("kit_id"),
            "device_id": first_decision.get("device_id"),
            "priority": first_decision.get("priority"),
            "recommended_action": first_decision.get("recommended_action"),
            "confidence": first_decision.get("confidence"),
            "created_at": first_decision.get("created_at"),
        }

    if predictions.get("items"):
        first_prediction = predictions["items"][0]
        frontend_view["last_prediction"] = {
            "prediction_id": first_prediction.get("prediction_id"),
            "client_id": first_prediction.get("client_id"),
            "kit_id": first_prediction.get("kit_id"),
            "device_id": first_prediction.get("device_id"),
            "risk_score": first_prediction.get("risk_score"),
            "risk_level": first_prediction.get("risk_level"),
            "alert_priority": first_prediction.get("alert_priority"),
            "predicted_at": first_prediction.get("predicted_at"),
        }
    _print_json_block("JSON lu par le frontend", frontend_view)

    print("\nPOUR EXPLORER LES DONNEES")
    print("=========================")
    print(f"Invoke-RestMethod {base}/v1/customers/{ids['client_id']}")
    print(f"Invoke-RestMethod \"{predictions_url}\"")
    print(f"Invoke-RestMethod \"{decisions_url}\"")
    print(f"Invoke-RestMethod {base}/realtime/devices/{ids['device_id']}/state")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simule le backend metier qui appelle /v1/customer/evaluate-from-telemetry."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="URL de base de l'API locale")
    parser.add_argument("--ticks", type=int, default=8, help="Nombre de payloads backend a envoyer")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Intervalle simule entre deux mesures")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pause reelle entre deux appels")
    parser.add_argument("--show-first-payload", action="store_true", help="Affiche le premier JSON envoye")
    parser.add_argument(
        "--fixed-demo-ids",
        action="store_true",
        help="Reutilise client-sim-001/device-sim-001. Par defaut, cree des IDs uniques pour une demo propre.",
    )
    parser.add_argument(
        "--payment-profile",
        choices=["good", "late"],
        default="good",
        help="Profil paiement brut envoye par le backend simule.",
    )
    parser.add_argument("--technical", action="store_true", help="Affiche aussi les noms de tables et IDs techniques.")
    args = parser.parse_args()

    endpoint = f"{args.api_url.rstrip('/')}/v1/customer/evaluate-from-telemetry"
    run_id = str(int(time.time()))
    ids = _demo_ids(run_id, fixed=args.fixed_demo_ids)
    base_timestamp = int(datetime(2026, 8, 21, 8, 0, tzinfo=UTC).timestamp())

    print("DEMO SIMPLE - Du backend jusqu'au frontend")
    print("==========================================")
    print("On simule un backend qui envoie les donnees d'un client et de son kit solaire.")
    print("")
    print("Histoire de la demo:")
    print(f"1. Le backend dit: le client {ids['client_id']} possede le kit {ids['kit_id']}.")
    print(f"2. Ce kit envoie ses mesures via le device {ids['device_id']}.")
    print("3. L'IA stocke chaque mesure et compare avec les anciennes mesures du meme device.")
    print("4. L'IA calcule le risque technique du kit et le risque paiement du client.")
    print("5. L'IA prend une decision et le frontend lit cette decision.")
    print("")
    print("Contexte de la simulation:")
    print(f"- Client        : {ids['client_id']}")
    print(f"- Kit           : {ids['kit_id']}")
    print(f"- Device        : {ids['device_id']}")
    print(f"- Nombre mesures: {args.ticks}")
    print(f"- Paiement      : {'bon payeur' if args.payment_profile == 'good' else 'retards de paiement'}")
    if args.technical:
        print(f"Endpoint       : {endpoint}")
    print("")

    for tick in range(args.ticks):
        payload = _payload_for_tick(
            tick,
            args.ticks,
            base_timestamp,
            args.interval_seconds,
            run_id,
            ids,
            args.payment_profile,
        )
        if tick == 0 and args.show_first_payload:
            print("Premier payload envoye par le backend simule")
            print("--------------------------------------------")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            print("")

        result = _safe_call("Evaluation client", post_json, endpoint, payload)
        _print_tick_result(tick, args.ticks, payload, result, technical=args.technical)
        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    _print_readback(args.api_url, ids, technical=args.technical)


if __name__ == "__main__":
    main()
