from __future__ import annotations

DEFAULT_PEAK_SUN_HOURS = {
    "kinshasa": 4.6,
    "brazzaville": 4.7,
    "lubumbashi": 5.2,
    "matadi": 4.5,
    "mbandaka": 4.2,
    "default": 4.5,
}

DEFAULT_RULES = {
    "system_loss_factor": 0.25,
    "battery_roundtrip_loss": 0.12,
    "growth_margin": 0.15,
    "uncertainty_margin": 0.10,
    "minimum_autonomy_hours": 8.0,
    "default_autonomy_hours": 12.0,
    "default_system_voltage_v": 24.0,
    "inverter_headroom": 1.25,
    "surge_headroom": 1.10,
    "controller_headroom": 1.25,
}

PREFERENCE_WEIGHTS = {
    "economy": {"price": 0.55, "autonomy": 0.15, "headroom": 0.30},
    "balanced": {"price": 0.35, "autonomy": 0.30, "headroom": 0.35},
    "performance": {"price": 0.20, "autonomy": 0.35, "headroom": 0.45},
    "autonomy": {"price": 0.20, "autonomy": 0.55, "headroom": 0.25},
}

DEMO_CURRENCY = "XAF"
