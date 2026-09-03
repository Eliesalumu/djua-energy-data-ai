from __future__ import annotations

import math

from djua_energy.solar_advisor.catalog import ComponentCatalog
from djua_energy.solar_advisor.constants import DEFAULT_PEAK_SUN_HOURS, DEFAULT_RULES
from djua_energy.solar_advisor.schemas import AdvisorRequest, ConsumptionProfile, SizingResult


class SizingEngine:
    def __init__(self, catalog: ComponentCatalog | None = None, rules: dict | None = None) -> None:
        self.catalog = catalog or ComponentCatalog()
        self.rules = {**DEFAULT_RULES, **(rules or {})}

    def size(self, request: AdvisorRequest, consumption: ConsumptionProfile) -> tuple[SizingResult, dict, list[dict]]:
        peak_sun_hours = self._peak_sun_hours(request)
        system_losses = self.rules["system_loss_factor"]
        required_pv = consumption.adjusted_daily_energy_wh / max(peak_sun_hours * (1 - system_losses), 0.1)
        panel = self.catalog.smallest_panel_at_least(required_pv / 2)
        panel_count = max(1, math.ceil(required_pv / max(panel.nominal_power_w, 1)))
        pv_total = panel_count * panel.nominal_power_w

        autonomy_hours = float(request.autonomy_hours or self.rules["default_autonomy_hours"])
        autonomy_energy_wh = consumption.adjusted_daily_energy_wh * (autonomy_hours / 24)
        battery_required_wh = autonomy_energy_wh / max(1 - self.rules["battery_roundtrip_loss"], 0.1)
        system_voltage = self.rules["default_system_voltage_v"] if consumption.simultaneous_power_w >= 600 else 12.0
        battery = self.catalog.choose_battery(battery_required_wh, system_voltage, request.preference)
        battery_capacity_wh = battery.capacity_wh or battery.capacity_ah * battery.voltage_v
        usable_battery_wh = battery_capacity_wh * max(battery.usable_depth_of_discharge, 0.5)
        battery_count = max(1, math.ceil(battery_required_wh / max(usable_battery_wh, 1)))
        bank_total_wh = battery_count * battery_capacity_wh
        bank_usable_wh = battery_count * usable_battery_wh

        inverter_needed = max(
            consumption.simultaneous_power_w * self.rules["inverter_headroom"],
            consumption.peak_starting_power_w * 0.65,
        )
        surge_needed = max(consumption.peak_starting_power_w * self.rules["surge_headroom"], inverter_needed)
        inverter = self.catalog.choose_inverter(inverter_needed, surge_needed)
        controller_current = (pv_total / max(system_voltage, 1)) * self.rules["controller_headroom"]
        controller = self.catalog.choose_controller(controller_current)

        sizing = SizingResult(
            peak_sun_hours=round(peak_sun_hours, 2),
            required_pv_power_w=round(required_pv, 2),
            panel_count=panel_count,
            panel_power_w=round(panel.nominal_power_w, 2),
            pv_total_power_w=round(pv_total, 2),
            battery_count=battery_count,
            battery_capacity_ah=round(battery.capacity_ah, 2),
            battery_voltage_v=round(battery.voltage_v, 2),
            battery_total_capacity_wh=round(bank_total_wh, 2),
            battery_usable_capacity_wh=round(bank_usable_wh, 2),
            autonomy_hours_estimated=round((bank_usable_wh / max(consumption.adjusted_daily_energy_wh, 1)) * 24, 2),
            inverter_power_w=round(inverter.inverter_continuous_power_w, 2),
            inverter_surge_power_w=round(inverter.inverter_surge_power_w, 2),
            controller_current_a=round(controller.controller_current_a, 2),
            system_voltage_v=round(system_voltage, 2),
            safety_margin=round(consumption.growth_margin + consumption.uncertainty_margin, 2),
        )
        selected = {
            "panel": panel.__dict__,
            "battery": battery.__dict__,
            "inverter": inverter.__dict__,
            "controller": controller.__dict__,
        }
        alternatives = self._alternatives(panel_count, battery_count, panel, battery, inverter, controller)
        return sizing, selected, alternatives

    def _peak_sun_hours(self, request: AdvisorRequest) -> float:
        key = (request.city or request.region or "default").lower()
        return DEFAULT_PEAK_SUN_HOURS.get(key, DEFAULT_PEAK_SUN_HOURS["default"])

    def _alternatives(self, panel_count, battery_count, panel, battery, inverter, controller) -> list[dict]:
        return [
            {
                "name": "option_economy",
                "description": "Configuration minimale avec les memes composants de demonstration.",
                "panel_count": max(1, panel_count - 1),
                "battery_count": max(1, battery_count),
                "estimated_price": round((max(1, panel_count - 1) * panel.unit_price) + battery_count * battery.unit_price + inverter.unit_price + controller.unit_price, 2),
            },
            {
                "name": "option_autonomy",
                "description": "Configuration avec une batterie supplementaire pour plus d'autonomie.",
                "panel_count": panel_count,
                "battery_count": battery_count + 1,
                "estimated_price": round(panel_count * panel.unit_price + (battery_count + 1) * battery.unit_price + inverter.unit_price + controller.unit_price, 2),
            },
        ]
