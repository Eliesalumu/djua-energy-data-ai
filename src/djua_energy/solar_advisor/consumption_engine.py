from __future__ import annotations

from djua_energy.solar_advisor.catalog import ApplianceCatalog
from djua_energy.solar_advisor.constants import DEFAULT_RULES
from djua_energy.solar_advisor.schemas import ApplianceConsumption, AdvisorRequest, ConsumptionProfile


class ConsumptionEngine:
    def __init__(self, catalog: ApplianceCatalog | None = None, rules: dict | None = None) -> None:
        self.catalog = catalog or ApplianceCatalog()
        self.rules = {**DEFAULT_RULES, **(rules or {})}

    def calculate(self, request: AdvisorRequest) -> ConsumptionProfile:
        rows: list[ApplianceConsumption] = []
        warnings: list[str] = []
        for need in request.appliances:
            catalog_item = self.catalog.find(need.name, need.appliance_id)
            assumptions: list[str] = []
            if catalog_item is None:
                power_w = float(need.power_w or 60)
                hours = float(need.hours_per_day or 4)
                duty_cycle = 1.0
                starting_power = power_w * 1.2
                confidence = "low"
                assumptions.append("Appareil absent du catalogue: estimation prudente a confirmer sur l'etiquette.")
                warnings.append(f"Puissance a confirmer pour {need.name}.")
            else:
                power_w = float(need.power_w or catalog_item.typical_power_w)
                hours = float(need.hours_per_day or catalog_item.average_daily_hours)
                duty_cycle = catalog_item.duty_cycle
                starting_power = max(catalog_item.starting_power_w, power_w * catalog_item.surge_multiplier)
                confidence = catalog_item.confidence_level
                if need.power_w is None:
                    assumptions.append(
                        f"Puissance typique utilisee pour {catalog_item.common_name_fr}: {power_w:.0f} W."
                    )
                if need.hours_per_day is None:
                    assumptions.append(f"Duree typique utilisee: {hours:.1f} h/jour.")
            quantity = max(1, int(need.quantity))
            daily_energy = quantity * power_w * hours * duty_cycle
            peak_power = quantity * power_w if need.simultaneous else power_w
            rows.append(
                ApplianceConsumption(
                    name=need.name,
                    quantity=quantity,
                    power_w=round(power_w, 2),
                    hours_per_day=round(hours, 2),
                    duty_cycle=round(duty_cycle, 3),
                    daily_energy_wh=round(daily_energy, 2),
                    peak_power_w=round(peak_power, 2),
                    starting_power_w=round(quantity * starting_power, 2),
                    usage_period=need.usage_period,
                    essential=need.essential,
                    confidence_level=confidence,
                    assumptions=assumptions,
                )
            )

        total = sum(item.daily_energy_wh for item in rows)
        day_energy = sum(item.daily_energy_wh for item in rows if item.usage_period in {"day", "mixed"})
        night_energy = sum(item.daily_energy_wh for item in rows if item.usage_period in {"night", "mixed"})
        uncertainty_margin = self.rules["uncertainty_margin"]
        growth_margin = self.rules["growth_margin"]
        adjusted = total * (1 + uncertainty_margin + growth_margin)
        return ConsumptionProfile(
            appliances=rows,
            total_daily_energy_wh=round(total, 2),
            total_daily_energy_kwh=round(total / 1000, 3),
            simultaneous_power_w=round(sum(item.peak_power_w for item in rows), 2),
            peak_starting_power_w=round(max([item.starting_power_w for item in rows] or [0]), 2),
            day_energy_wh=round(day_energy, 2),
            night_energy_wh=round(night_energy, 2),
            essential_energy_wh=round(sum(item.daily_energy_wh for item in rows if item.essential), 2),
            optional_energy_wh=round(sum(item.daily_energy_wh for item in rows if not item.essential), 2),
            uncertainty_margin=uncertainty_margin,
            growth_margin=growth_margin,
            adjusted_daily_energy_wh=round(adjusted, 2),
            warnings=warnings,
        )
