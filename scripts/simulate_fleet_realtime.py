from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.pipeline.contracts import validate_payload

SECONDS_PER_MONTH = 30 * 24 * 60 * 60


REGIONS = [
    {
        "name": "dakar_periurban",
        "lat": 14.7167,
        "lon": -17.4677,
        "ambient_base_c": 31.0,
        "humidity_base_pct": 72.0,
        "irradiance_base": 760.0,
        "network_quality": "good",
        "security_risk_zone": "high",
    },
    {
        "name": "thies_dry_inland",
        "lat": 14.7910,
        "lon": -16.9359,
        "ambient_base_c": 35.0,
        "humidity_base_pct": 45.0,
        "irradiance_base": 900.0,
        "network_quality": "medium",
        "security_risk_zone": "medium",
    },
    {
        "name": "saint_louis_sahel",
        "lat": 16.0326,
        "lon": -16.4818,
        "ambient_base_c": 36.5,
        "humidity_base_pct": 38.0,
        "irradiance_base": 940.0,
        "network_quality": "weak",
        "security_risk_zone": "medium",
    },
    {
        "name": "ziguinchor_humid",
        "lat": 12.5680,
        "lon": -16.2733,
        "ambient_base_c": 29.0,
        "humidity_base_pct": 84.0,
        "irradiance_base": 650.0,
        "network_quality": "medium",
        "security_risk_zone": "low",
    },
    {
        "name": "tambacounda_hot_inland",
        "lat": 13.7707,
        "lon": -13.6673,
        "ambient_base_c": 38.0,
        "humidity_base_pct": 34.0,
        "irradiance_base": 930.0,
        "network_quality": "medium",
        "security_risk_zone": "high",
    },
    {
        "name": "kaolack_shared_kiosk",
        "lat": 14.1652,
        "lon": -16.0758,
        "ambient_base_c": 34.0,
        "humidity_base_pct": 55.0,
        "irradiance_base": 850.0,
        "network_quality": "good",
        "security_risk_zone": "medium",
    },
]

SEASON_BY_MONTH = {
    1: "dry",
    2: "dry",
    3: "dry",
    4: "transition",
    5: "transition",
    6: "rainy",
    7: "rainy",
    8: "rainy",
    9: "rainy",
    10: "transition",
    11: "dry",
    12: "harmattan",
}

SEASON_EFFECTS = {
    "dry": {"temp_delta": 3.0, "humidity_delta": -12.0, "irradiance_factor": 1.10},
    "rainy": {"temp_delta": -2.0, "humidity_delta": 16.0, "irradiance_factor": 0.58},
    "harmattan": {"temp_delta": 1.0, "humidity_delta": -22.0, "irradiance_factor": 0.78},
    "transition": {"temp_delta": 0.0, "humidity_delta": 0.0, "irradiance_factor": 0.92},
}

INSTALLATION_TYPES = {
    "household_rooftop": {"solar_factor": 1.0, "temp_delta": 0.0, "load_factor": 1.0},
    "ground_mount": {"solar_factor": 1.08, "temp_delta": -0.8, "load_factor": 0.95},
    "kiosk_shared": {"solar_factor": 0.92, "temp_delta": 1.2, "load_factor": 1.35},
    "mobile_asset": {"solar_factor": 0.82, "temp_delta": 1.5, "load_factor": 1.15},
}

USAGE_PROFILES = {
    "low": {"load_factor": 0.75},
    "normal": {"load_factor": 1.0},
    "intensive": {"load_factor": 1.35},
}

SCENARIO_DESCRIPTIONS = {
    "normal": "Stable device with normal battery, solar input and security signals.",
    "battery_degradation": "Battery health and charge decrease faster than expected.",
    "overheating": "Battery and internal temperatures rise under hot climate/load.",
    "low_solar_input": "Solar production stays weak; battery slowly loses autonomy.",
    "security_movement": "Device moves away from its authorized location.",
    "connectivity_loss": "Network quality degrades and telemetry gaps increase.",
}

RISK_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0, "n/a": 0}

SCENARIO_TITLES = {
    "normal": "Fonctionnement normal",
    "battery_degradation": "Degradation batterie",
    "overheating": "Surchauffe batterie",
    "low_solar_input": "Production solaire faible",
    "security_movement": "Deplacement suspect",
    "connectivity_loss": "Perte de connectivite",
}

SCENARIO_ACTIONS = {
    "normal": "Continuer la supervision standard.",
    "battery_degradation": "Planifier un controle batterie et verifier l'autonomie reelle.",
    "overheating": "Inspecter batterie, ventilation, regulateur et exposition au soleil.",
    "low_solar_input": "Verifier panneau solaire, orientation, ombrage et connectique.",
    "security_movement": "Verifier physiquement le kit et confirmer la position GPS.",
    "connectivity_loss": "Controler reseau/SIM/antenne et recuperer les messages en attente.",
}

ALERT_ACTION_TRANSLATIONS = {
    "Dispatch field team immediately.": "Envoyer une equipe terrain immediatement.",
    "Create urgent intervention ticket.": "Creer un ticket d'intervention urgent.",
    "Schedule technical inspection.": "Programmer une inspection technique.",
    "Monitor device.": "Surveiller le device.",
    "No alert required.": "",
}


@dataclass
class DeviceState:
    device_id: str
    kit_id: str
    serial_number: str
    region: dict[str, Any]
    installation_type: str
    usage_profile: str
    scenario: str
    initial_battery_age_months: float
    battery_capacity_ah: float
    state_of_charge_pct: float
    state_of_health_pct: float
    base_latitude: float
    base_longitude: float
    latitude: float
    longitude: float
    reset_count: int = 0
    total_energy_generated_wh: float = 0.0
    total_energy_consumed_wh: float = 0.0


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def season_for_timestamp(timestamp: int) -> str:
    month = time.gmtime(timestamp).tm_mon
    return SEASON_BY_MONTH.get(month, "dry")


def day_context(timestamp: int) -> tuple[str, float]:
    hour = time.gmtime(timestamp).tm_hour + time.gmtime(timestamp).tm_min / 60
    if hour < 6 or hour >= 19:
        return "night", 0.02
    daylight_progress = (hour - 6) / 13
    return "day", max(0.08, math.sin(math.pi * daylight_progress))


def build_fleet(num_devices: int, seed: int) -> list[DeviceState]:
    rng = Random(seed)
    scenario_cycle = list(SCENARIO_DESCRIPTIONS)
    installation_cycle = list(INSTALLATION_TYPES)
    usage_cycle = ["normal", "intensive", "normal", "low", "normal", "intensive"]
    fleet: list[DeviceState] = []
    for index in range(num_devices):
        region = REGIONS[index % len(REGIONS)]
        lat = region["lat"] + rng.uniform(-0.018, 0.018)
        lon = region["lon"] + rng.uniform(-0.018, 0.018)
        scenario = scenario_cycle[index % len(scenario_cycle)]
        age_months = 3 + ((index * 9) % 54) + rng.uniform(0, 0.8)
        soh = clamp(99.0 - age_months * 0.42, 62.0, 99.0)
        soc = clamp(88.0 - index * 4.5 + rng.uniform(-2.0, 2.0), 42.0, 96.0)
        fleet.append(
            DeviceState(
                device_id=f"device-{index + 1:03d}",
                kit_id=f"kit-{index + 1:03d}",
                serial_number=f"DJUA-SN-{index + 1:05d}",
                region=region,
                installation_type=installation_cycle[index % len(installation_cycle)],
                usage_profile=usage_cycle[index % len(usage_cycle)],
                scenario=scenario,
                initial_battery_age_months=age_months,
                battery_capacity_ah=80.0,
                state_of_charge_pct=soc,
                state_of_health_pct=soh,
                base_latitude=lat,
                base_longitude=lon,
                latitude=lat,
                longitude=lon,
            )
        )
    return fleet


def climate_for(device: DeviceState, timestamp: int, tick: int, rng: Random) -> dict[str, Any]:
    season = season_for_timestamp(timestamp)
    season_effect = SEASON_EFFECTS[season]
    day_period, solar_day_factor = day_context(timestamp)
    installation = INSTALLATION_TYPES[device.installation_type]
    weather_wave = math.sin((tick / 6.0) + (len(device.device_id) * 0.3))
    cloud_factor = clamp(0.78 + 0.18 * math.sin(tick / 4.0) + rng.uniform(-0.08, 0.08), 0.35, 1.08)
    ambient = (
        device.region["ambient_base_c"]
        + season_effect["temp_delta"]
        + installation["temp_delta"]
        + 2.4 * weather_wave
        + rng.uniform(-0.7, 0.7)
    )
    humidity = (
        device.region["humidity_base_pct"]
        + season_effect["humidity_delta"]
        - 0.9 * max(0.0, ambient - 32.0)
        + rng.uniform(-3.5, 3.5)
    )
    irradiance = (
        device.region["irradiance_base"]
        * season_effect["irradiance_factor"]
        * solar_day_factor
        * installation["solar_factor"]
        * cloud_factor
    )
    return {
        "season": season,
        "day_period": day_period,
        "ambient_temperature_c": round(clamp(ambient, 18.0, 48.0), 2),
        "humidity_pct": round(clamp(humidity, 12.0, 98.0), 2),
        "solar_irradiance_w_m2": round(clamp(irradiance, 0.0, 1120.0), 2),
    }


def security_for(device: DeviceState, tick: int) -> dict[str, Any]:
    movement = False
    tamper = False
    enclosure_opened = False
    impact = False
    speed = 0.0
    distance = 0.0
    lat = device.base_latitude
    lon = device.base_longitude

    if device.scenario == "security_movement" and tick >= 4:
        movement = True
        distance = min(240.0, 35.0 + (tick - 3) * 18.0)
        speed = 0.45
        lat = device.base_latitude + distance / 111_000
        lon = device.base_longitude + distance / 111_000
        tamper = tick in {7, 8}
        enclosure_opened = tick in {8, 9}
        impact = tick == 8

    device.latitude = lat
    device.longitude = lon
    geofence_status = "outside" if distance > 50.0 else "inside"
    return {
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "gps_accuracy_m": 7.5 if movement else 3.5,
        "gps_fix_status": "fixed",
        "speed_mps": speed,
        "heading_deg": 40.0 if movement else 0.0,
        "distance_from_installation_m": round(distance, 2),
        "authorized_radius_m": 50.0,
        "movement_detected": movement,
        "movement_duration_seconds": 300 if movement else 0,
        "movement_event_count": 1 if movement else 0,
        "tilt_angle_deg": 18.0 if impact else 0.0,
        "impact_detected": impact,
        "geofence_status": geofence_status,
        "tamper_detected": tamper,
        "enclosure_opened": enclosure_opened,
        "cable_disconnection_detected": False,
        "unauthorized_power_cycle_detected": tamper,
        "security_event_code": "TAMPER_OPEN" if enclosure_opened else ("MOVEMENT" if movement else "NONE"),
        "security_event_time": None,
        "tamper_sensor_status": "ok",
        "enclosure_sensor_status": "ok",
        "asset_lock_status": "unlocked" if enclosure_opened else "locked",
        "identity_mismatch_detected": bool(device.scenario == "security_movement" and tick >= 8),
    }


def connectivity_for(device: DeviceState, tick: int) -> dict[str, Any]:
    quality = device.region["network_quality"]
    gap = {"good": 0, "medium": 70, "weak": 180}[quality]
    if device.scenario == "connectivity_loss":
        if tick >= 4:
            quality = "weak"
            gap = 180 + (tick - 4) * 35
        if tick >= 10:
            gap = 420
    status = "connected" if gap < 60 else ("degraded" if gap < 300 else "disconnected")
    return {
        "network_quality": quality,
        "connectivity_type": "lte",
        "connection_status": status,
        "signal_strength_dbm": -67 if quality == "good" else (-84 if quality == "medium" else -101),
        "network_operator": "synthetic-op" if tick < 9 else ("synthetic-op-alt" if device.scenario == "security_movement" else "synthetic-op"),
        "sim_identifier_hash": f"sim-{device.device_id}",
        "network_cell_id_hash": f"cell-{device.region['name']}",
        "queued_messages": 0 if status != "disconnected" else 3,
        "retry_count": 0 if status == "connected" else 2,
        "connectivity_gap_seconds": int(gap),
        "packet_loss_ratio": 0.0 if quality == "good" else (0.08 if quality == "medium" else 0.22),
        "data_usage_bytes": 512,
        "is_buffered_message": status == "disconnected",
        "buffered_at": None,
        "transmission_attempt": 1 if status == "connected" else 2,
    }


def update_power_state(
    device: DeviceState,
    climate: dict[str, Any],
    tick: int,
    interval_seconds: int,
    elapsed_seconds: int,
) -> dict[str, Any]:
    installation = INSTALLATION_TYPES[device.installation_type]
    usage = USAGE_PROFILES[device.usage_profile]
    hours = interval_seconds / 3600
    solar_power = climate["solar_irradiance_w_m2"] * 0.19 * installation["solar_factor"]
    load_power = 42.0 * usage["load_factor"] * installation["load_factor"]
    load_power += 8.0 * max(0.0, math.sin(tick / 3.0))

    if device.scenario == "low_solar_input":
        solar_power *= 0.34
    if device.scenario == "battery_degradation":
        load_power *= 1.08
    if device.scenario == "overheating":
        load_power *= 1.18

    generated_wh = max(0.0, solar_power * hours * 0.88)
    consumed_wh = max(0.0, load_power * hours)
    net_wh = generated_wh - consumed_wh
    usable_capacity_wh = 12.8 * device.battery_capacity_ah * max(0.45, device.state_of_health_pct / 100)
    soc_delta = (net_wh / usable_capacity_wh) * 100
    if device.scenario == "battery_degradation":
        soc_delta -= 0.38
    if device.scenario == "connectivity_loss":
        soc_delta -= 0.05
    device.state_of_charge_pct = clamp(device.state_of_charge_pct + soc_delta, 5.0, 100.0)

    temp_stress = max(0.0, climate["ambient_temperature_c"] - 38.0) * 0.0008
    scenario_wear = 0.006 if device.scenario == "battery_degradation" else 0.0
    device.state_of_health_pct = clamp(device.state_of_health_pct - scenario_wear - temp_stress, 45.0, 100.0)
    device.total_energy_generated_wh += generated_wh
    device.total_energy_consumed_wh += consumed_wh

    age_months = device.initial_battery_age_months + elapsed_seconds / SECONDS_PER_MONTH
    battery_voltage = 11.65 + (device.state_of_charge_pct / 100) * 1.75 - age_months * 0.004
    if device.scenario == "battery_degradation":
        battery_voltage -= min(0.45, tick * 0.018)
    battery_temperature = climate["ambient_temperature_c"] + 2.0 + load_power * 0.025
    if device.scenario == "overheating":
        battery_temperature += 7.0 + min(5.5, tick * 0.35)
    device_temperature = battery_temperature + 1.4
    battery_current = max(0.2, load_power / max(11.5, battery_voltage))

    return {
        "battery_age_months": round(age_months, 4),
        "battery_voltage_v": round(clamp(battery_voltage, 10.8, 13.8), 2),
        "battery_current_a": round(battery_current, 2),
        "battery_power_w": round(clamp(battery_voltage, 10.8, 13.8) * battery_current, 2),
        "battery_temperature_c": round(clamp(battery_temperature, 15.0, 62.0), 2),
        "state_of_charge_pct": round(device.state_of_charge_pct, 2),
        "state_of_health_pct": round(device.state_of_health_pct, 2),
        "battery_cycle_count": round(120 + age_months * 8 + tick * 0.03, 2),
        "battery_capacity_ah": device.battery_capacity_ah,
        "battery_remaining_capacity_ah": round(device.battery_capacity_ah * device.state_of_charge_pct / 100, 2),
        "charging_status": "charging" if net_wh > 0 else "discharging",
        "charge_duration_seconds": interval_seconds if net_wh > 0 else 0,
        "discharge_duration_seconds": 0 if net_wh > 0 else interval_seconds,
        "battery_error_code": "BATT_TEMP_HIGH" if battery_temperature >= 45 else "NONE",
        "battery_controller_status": "warning" if battery_temperature >= 45 else "ok",
        "solar_voltage_v": 22.0,
        "solar_current_a": round(max(0.0, solar_power / 22.0), 2),
        "solar_power_w": round(max(0.0, solar_power), 2),
        "energy_generated_wh": round(device.total_energy_generated_wh, 2),
        "panel_temperature_c": round(climate["ambient_temperature_c"] + 8.0, 2),
        "solar_controller_status": "ok",
        "solar_error_code": "LOW_SOLAR" if device.scenario == "low_solar_input" and solar_power < 35 else "NONE",
        "load_voltage_v": 12.0,
        "load_current_a": round(max(0.1, load_power / 12.0), 2),
        "load_power_w": round(load_power, 2),
        "energy_consumed_wh": round(device.total_energy_consumed_wh, 2),
        "peak_load_power_w": round(load_power + 12.0, 2),
        "load_status": "ok",
        "overload_detected": load_power > 95,
        "short_circuit_detected": False,
        "output_enabled": True,
        "abnormal_consumption_detected": device.usage_profile == "intensive" or load_power > 80,
        "device_temperature_c": round(device_temperature, 2),
    }


def build_record(
    device: DeviceState,
    *,
    tick: int,
    timestamp: int,
    interval_seconds: int,
    start_time: int,
    run_id: str,
    seed: int,
) -> dict[str, Any]:
    rng = Random(seed + tick * 1009 + int(device.device_id.split("-")[-1]))
    elapsed_seconds = timestamp - start_time
    climate = climate_for(device, timestamp, tick, rng)
    power = update_power_state(device, climate, tick, interval_seconds, elapsed_seconds)
    security = security_for(device, tick)
    connectivity = connectivity_for(device, tick)
    if security["tamper_detected"] and device.reset_count == 0:
        device.reset_count += 1

    record = {
        "message_id": f"fleet-{run_id}-{device.device_id}-{tick + 1:04d}",
        "schema_version": "1.0",
        "message_type": "telemetry",
        "device_id": device.device_id,
        "kit_id": device.kit_id,
        "serial_number": device.serial_number,
        "device_model": "djua-solar-v2-simulated",
        "hardware_revision": "rev-b",
        "firmware_version": "1.1.0",
        "boot_id": f"boot-{device.device_id}",
        "event_time": str(timestamp),
        "ingestion_time": str(timestamp + 10),
        "last_successful_sync_at": str(timestamp if connectivity["connection_status"] != "disconnected" else timestamp - connectivity["connectivity_gap_seconds"]),
        "sequence_number": tick + 1,
        "sampling_interval_seconds": interval_seconds,
        "synthetic_data": True,
        "simulation_name": "fleet_realtime_v1",
        "scenario": device.scenario,
        "scenario_description": SCENARIO_DESCRIPTIONS[device.scenario],
        "metadata": {"source": "synthetic_fleet_realtime", "contract": "telemetry.v1"},
        "region": device.region["name"],
        "installation_type": device.installation_type,
        "usage_profile": device.usage_profile,
        "security_risk_zone": device.region["security_risk_zone"],
        **climate,
        **power,
        **security,
        **connectivity,
        "altitude_m": 35.0,
        "device_uptime_seconds": 100000 + tick * interval_seconds,
        "cpu_usage_pct": 22 + (tick % 5) * 3,
        "memory_usage_pct": 38 + (tick % 4) * 4,
        "storage_usage_pct": 24 + (tick % 8),
        "reset_reason": "TAMPER" if security["tamper_detected"] else "NONE",
        "reset_count": device.reset_count,
        "watchdog_reset_count": 0,
        "brownout_detected": False,
        "device_error_code": "NONE",
        "internal_clock_status": "ok",
        "local_storage_status": "ok",
        "sensor_status": "ok",
        "measurement_quality": "good",
        "sensor_calibration_version": "1.0",
        "calibration_date": "2026-01-01",
        "missing_measurement_count": 0,
        "invalid_measurement_count": 0,
        "sensor_failure_detected": connectivity["connection_status"] == "disconnected",
        "quality_flag": "ok",
        "data_completeness_pct": 100.0,
    }
    validation = validate_payload(record)
    if not validation["valid"]:
        raise ValueError(f"Invalid generated record for {device.device_id}: {validation['errors']}")
    return record


def build_records(
    *,
    cycles: int,
    interval_seconds: int,
    devices: int,
    seed: int,
    start_time: int,
    run_id: str,
) -> list[dict[str, Any]]:
    fleet = build_fleet(devices, seed)
    records: list[dict[str, Any]] = []
    for tick in range(cycles):
        timestamp = start_time + tick * interval_seconds
        for device in fleet:
            records.append(
                build_record(
                    device,
                    tick=tick,
                    timestamp=timestamp,
                    interval_seconds=interval_seconds,
                    start_time=start_time,
                    run_id=run_id,
                    seed=seed,
                )
            )
    return records


def print_dry_run(records: list[dict[str, Any]], devices: int) -> None:
    print("Dry-run: generated payloads only, nothing was sent to the API.")
    print(f"Records generated : {len(records)}")
    print(f"Devices simulated : {devices}")
    print("")
    for record in records[: min(len(records), devices * 3)]:
        print(
            f"{record['device_id']} seq={record['sequence_number']:02d} "
            f"scenario={record['scenario']} soc={record['state_of_charge_pct']}% "
            f"soh={record['state_of_health_pct']}% age={record['battery_age_months']}m "
            f"temp_batt={record['battery_temperature_c']}C ambient={record['ambient_temperature_c']}C "
            f"solar={record['solar_power_w']}W load={record['load_power_w']}W "
            f"gps=({record['latitude']},{record['longitude']}) geofence={record['geofence_status']}"
        )


def fmt_time(timestamp: str | int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(timestamp)))


def risk_label_fr(risk_level: Any) -> str:
    value = str(risk_level or "none").lower()
    return {
        "critical": "CRITIQUE",
        "high": "ELEVE",
        "medium": "MOYEN",
        "low": "FAIBLE",
        "none": "AUCUNE ALERTE",
        "n/a": "NON DISPONIBLE",
    }.get(value, value.upper())


def scenario_title(scenario: str) -> str:
    return SCENARIO_TITLES.get(scenario, scenario.replace("_", " ").title())


def trend_arrow(current: float, previous: float | None, *, inverse: bool = False) -> str:
    if previous is None:
        return "stable"
    delta = current - previous
    if abs(delta) < 0.05:
        return "stable"
    getting_worse = delta < 0 if inverse else delta > 0
    direction = "baisse" if delta < 0 else "hausse"
    return f"{direction} {'defavorable' if getting_worse else 'favorable'} ({delta:+.2f})"


def evidence_for(record: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    evidence: list[str] = []
    scenario = str(record.get("scenario", ""))
    if scenario == "normal":
        evidence.append(
            f"Batterie stable: SOC {record['state_of_charge_pct']}%, temperature {record['battery_temperature_c']}C."
        )
    if record["battery_temperature_c"] >= 45:
        evidence.append(
            f"Surchauffe: batterie {record['battery_temperature_c']}C pour ambiance {record['ambient_temperature_c']}C."
        )
    if scenario == "battery_degradation":
        evidence.append(
            "Autonomie en degradation: "
            f"SOC {record['state_of_charge_pct']}% ({trend_arrow(record['state_of_charge_pct'], previous.get('soc') if previous else None, inverse=True)}), "
            f"sante {record['state_of_health_pct']}%."
        )
    if scenario == "low_solar_input" or record["solar_power_w"] < record["load_power_w"]:
        evidence.append(
            f"Bilan energie defavorable: solaire {record['solar_power_w']}W vs charge {record['load_power_w']}W."
        )
    if record["geofence_status"] == "outside":
        evidence.append(
            f"Position anormale: {record['distance_from_installation_m']} m du point installe, geofence outside."
        )
    if record["tamper_detected"] or record["enclosure_opened"]:
        evidence.append("Securite physique: mouvement/tamper/ouverture boitier detecte.")
    if record["connection_status"] == "disconnected":
        evidence.append(f"Device hors ligne: silence reseau {record['connectivity_gap_seconds']} secondes.")
    elif record["connection_status"] == "degraded":
        evidence.append(f"Reseau degrade: gap {record['connectivity_gap_seconds']} secondes.")
    if previous and previous.get("geofence") == "inside" and record["geofence_status"] == "outside":
        evidence.append("Changement important: le device vient de sortir de sa zone autorisee.")
    if previous and previous.get("connection") != "disconnected" and record["connection_status"] == "disconnected":
        evidence.append("Changement important: le device vient de passer hors ligne.")
    return evidence[:3]


def operational_status(record: dict[str, Any], risk_level: str) -> str:
    if record["connection_status"] == "disconnected":
        return "Communication perdue"
    if record["geofence_status"] == "outside" or record["tamper_detected"] or record["enclosure_opened"]:
        return "Risque securite terrain"
    if record["battery_temperature_c"] >= 45:
        return "Risque thermique batterie"
    if str(risk_level).lower() in {"critical", "high"}:
        return "Intervention prioritaire"
    if str(risk_level).lower() == "medium":
        return "Surveillance renforcee"
    return "Situation sous controle"


def action_for(record: dict[str, Any], alert_action: Any) -> str:
    translated_alert_action = ALERT_ACTION_TRANSLATIONS.get(str(alert_action), str(alert_action or ""))
    if translated_alert_action:
        return translated_alert_action
    return SCENARIO_ACTIONS.get(str(record.get("scenario")), "Analyser le device et suivre son evolution.")


def should_show_device(
    record: dict[str, Any],
    risk_level: str,
    previous: dict[str, Any] | None,
    tick: int,
    final_tick: int,
) -> bool:
    if tick in {0, final_tick}:
        return True
    if RISK_RANK.get(str(risk_level).lower(), 0) >= RISK_RANK["medium"]:
        return True
    if record["geofence_status"] == "outside" or record["connection_status"] == "disconnected":
        return True
    if record["battery_temperature_c"] >= 45:
        return True
    if previous and previous.get("geofence") != record["geofence_status"]:
        return True
    if previous and previous.get("connection") != record["connection_status"]:
        return True
    return False


def print_tick_header(tick: int, cycles_label: str, tick_records: list[dict[str, Any]]) -> None:
    timestamp = fmt_time(tick_records[0]["event_time"])
    simulated_minute = tick * int(tick_records[0]["sampling_interval_seconds"]) // 60
    print("")
    print("=" * 90)
    print(f"TICK {tick + 1:02d}/{cycles_label} | Temps simule +{simulated_minute} min | {timestamp}")
    print("=" * 90)


def print_device_decision(
    record: dict[str, Any],
    *,
    risk_level: str,
    risk_score: Any,
    action: str,
    previous: dict[str, Any] | None,
) -> None:
    print(f"{record['device_id']} - {scenario_title(record['scenario'])}")
    print(f"  Lecture terrain : {operational_status(record, risk_level)}")
    print(f"  Score modele IA : risque {risk_label_fr(risk_level)} | score {risk_score}/100")
    print(
        "  Mesures clefs: "
        f"SOC {record['state_of_charge_pct']}%, SOH {record['state_of_health_pct']}%, "
        f"batt {record['battery_temperature_c']}C, ambiant {record['ambient_temperature_c']}C, "
        f"solaire {record['solar_power_w']}W, charge {record['load_power_w']}W"
    )
    print(
        "  Terrain      : "
        f"region {record['region']}, GPS ({record['latitude']}, {record['longitude']}), "
        f"geofence {record['geofence_status']}, reseau {record['connection_status']}"
    )
    for index, item in enumerate(evidence_for(record, previous), start=1):
        print(f"  Preuve {index}     : {item}")
    print(f"  Action      : {action}")


def device_state_snapshot(record: dict[str, Any], risk_level: str, risk_score: Any, action: str) -> dict[str, Any]:
    return {
        "scenario": record["scenario"],
        "soc": float(record["state_of_charge_pct"]),
        "soh": float(record["state_of_health_pct"]),
        "battery_temp": float(record["battery_temperature_c"]),
        "ambient": float(record["ambient_temperature_c"]),
        "solar": float(record["solar_power_w"]),
        "load": float(record["load_power_w"]),
        "geofence": record["geofence_status"],
        "connection": record["connection_status"],
        "distance": float(record["distance_from_installation_m"]),
        "risk_level": risk_level,
        "risk_score": risk_score,
        "action": action,
        "event_time": record["event_time"],
        "latitude": record["latitude"],
        "longitude": record["longitude"],
    }


def print_final_summary(by_device: dict[str, dict[str, Any]], processed: int, api_url: str) -> None:
    print("")
    print("=" * 90)
    print("SYNTHESE FINALE - Lecture jury")
    print("=" * 90)
    print(f"Mesures traitees : {processed}")
    print(f"Devices analyses : {len(by_device)}")
    print("")
    ordered = sorted(
        by_device.items(),
        key=lambda item: (RISK_RANK.get(str(item[1]["risk_level"]).lower(), 0), float(item[1]["risk_score"] or 0)),
        reverse=True,
    )
    for device_id, state in ordered:
        print(f"{device_id} | {scenario_title(state['scenario'])}")
        print(f"  Score IA     : risque {risk_label_fr(state['risk_level'])}, score {state['risk_score']}/100")
        print(
            f"  Situation    : SOC {state['soc']}%, SOH {state['soh']}%, "
            f"temp {state['battery_temp']}C, reseau {state['connection']}, geofence {state['geofence']}"
        )
        print(f"  Decision     : {state['action']}")
    print("")
    print("Pour verifier la base temps reel :")
    print(f"Invoke-RestMethod {api_url.rstrip('/')}/realtime/fleet-state")
    print(f"Invoke-RestMethod {api_url.rstrip('/')}/realtime/devices/device-001/predictions")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate several Djua Energy devices sending complete telemetry every 5 minutes."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Local FastAPI base URL.")
    parser.add_argument("--devices", type=int, default=6, help="Number of devices in the simulated fleet.")
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of telemetry ticks per device. Use 0 to run continuously until Ctrl+C.",
    )
    parser.add_argument("--interval-seconds", type=int, default=300, help="Simulated time between two ticks.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Real pause between ticks.")
    parser.add_argument("--seed", type=int, default=20260727, help="Deterministic simulation seed.")
    parser.add_argument("--start-time", type=int, default=0, help="Epoch timestamp for the first tick; default is now.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate payloads without sending them.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.devices <= 0:
        raise SystemExit("--devices must be positive")
    if args.cycles < 0:
        raise SystemExit("--cycles must be zero or positive")
    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be positive")

    start_time = args.start_time or int(time.time())
    run_id = str(start_time)
    continuous = args.cycles == 0
    cycles_label = "continu" if continuous else str(args.cycles)
    fleet = build_fleet(args.devices, args.seed)
    records = []
    if not continuous:
        records = build_records(
            cycles=args.cycles,
            interval_seconds=args.interval_seconds,
            devices=args.devices,
            seed=args.seed,
            start_time=start_time,
            run_id=run_id,
        )

    print("Djua Energy - Fleet realtime simulation")
    print("=======================================")
    print(f"API endpoint       : {args.api_url.rstrip('/')}/telemetry/analyze")
    print(f"Devices simulated : {args.devices}")
    print(f"Ticks per device   : {cycles_label}")
    print(f"Interval simulated : {args.interval_seconds} seconds")
    print(f"Real pause         : {args.sleep_seconds} seconds")
    print(f"Records total      : {'continuous' if continuous else len(records)}")
    if continuous:
        print("Stop simulation    : press Ctrl+C")
    print("")

    if args.dry_run:
        if continuous:
            records = build_records(
                cycles=3,
                interval_seconds=args.interval_seconds,
                devices=args.devices,
                seed=args.seed,
                start_time=start_time,
                run_id=run_id,
            )
        print_dry_run(records, args.devices)
        return

    endpoint = f"{args.api_url.rstrip('/')}/telemetry/analyze"
    processed = 0
    by_device: dict[str, dict[str, Any]] = {}
    previous_by_device: dict[str, dict[str, Any]] = {}
    tick = 0
    try:
        while continuous or tick < args.cycles:
            timestamp = start_time + tick * args.interval_seconds
            if continuous:
                tick_records = [
                    build_record(
                        device,
                        tick=tick,
                        timestamp=timestamp,
                        interval_seconds=args.interval_seconds,
                        start_time=start_time,
                        run_id=run_id,
                        seed=args.seed,
                    )
                    for device in fleet
                ]
            else:
                tick_records = records[tick * args.devices : (tick + 1) * args.devices]

            print_tick_header(tick, cycles_label, tick_records)
            shown = 0
            for record in tick_records:
                try:
                    result = post_json(endpoint, {"records": [record]})
                except URLError as exc:
                    print("")
                    print("Cannot reach the local API.")
                    print("Start it with:")
                    print(".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload")
                    raise SystemExit(1) from exc

                stored = result.get("stored_prediction") or {}
                alert = result.get("alert") or {}
                risk_level = stored.get("risk_level", alert.get("priority", "n/a"))
                risk_score = stored.get("risk_score", "n/a")
                action = action_for(record, stored.get("recommended_action") or alert.get("recommended_action"))
                previous = previous_by_device.get(record["device_id"])
                snapshot = device_state_snapshot(record, risk_level, risk_score, action)
                by_device[record["device_id"]] = snapshot
                previous_by_device[record["device_id"]] = snapshot
                processed += 1
                if should_show_device(record, risk_level, previous, tick, -1 if continuous else args.cycles - 1):
                    print_device_decision(
                        record,
                        risk_level=risk_level,
                        risk_score=risk_score,
                        action=action,
                        previous=previous,
                    )
                    shown += 1
            if shown == 0:
                print("Aucun changement critique affiche sur ce tick. La flotte continue a etre surveillee.")
            tick += 1
            if args.sleep_seconds:
                time.sleep(args.sleep_seconds)
    except KeyboardInterrupt:
        print("")
        print("Simulation arretee manuellement par l'utilisateur.")

    print_final_summary(by_device, processed, args.api_url)


if __name__ == "__main__":
    main()
