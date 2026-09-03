from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApplianceCatalogItem:
    appliance_id: str
    category: str
    name: str
    common_name_fr: str
    typical_power_w: float
    standby_power_w: float
    starting_power_w: float
    surge_multiplier: float
    average_daily_hours: float
    duty_cycle: float
    min_power_w: float
    max_power_w: float
    confidence_level: str
    notes: str = ""


@dataclass(frozen=True)
class Component:
    component_id: str
    component_type: str
    manufacturer: str
    model: str
    nominal_power_w: float = 0.0
    capacity_ah: float = 0.0
    capacity_wh: float = 0.0
    voltage_v: float = 0.0
    chemistry: str = ""
    usable_depth_of_discharge: float = 0.0
    efficiency: float = 1.0
    inverter_continuous_power_w: float = 0.0
    inverter_surge_power_w: float = 0.0
    controller_type: str = ""
    controller_current_a: float = 0.0
    unit_price: float = 0.0
    currency: str = "XAF"
    stock_status: str = "demo"
    compatible_system_voltage: str = ""
    is_synthetic: bool = True


@dataclass(frozen=True)
class ApplianceNeed:
    name: str
    quantity: int = 1
    hours_per_day: float | None = None
    power_w: float | None = None
    usage_period: str = "mixed"
    essential: bool = True
    simultaneous: bool = True
    appliance_id: str | None = None


@dataclass(frozen=True)
class AdvisorRequest:
    customer_id: str | None
    city: str | None
    region: str | None
    housing_type: str | None
    people_count: int | None
    autonomy_hours: float | None
    budget: float | None
    preference: str
    appliances: list[ApplianceNeed]
    source: str = "manual"
    contact: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApplianceConsumption:
    name: str
    quantity: int
    power_w: float
    hours_per_day: float
    duty_cycle: float
    daily_energy_wh: float
    peak_power_w: float
    starting_power_w: float
    usage_period: str
    essential: bool
    confidence_level: str
    assumptions: list[str]


@dataclass(frozen=True)
class ConsumptionProfile:
    appliances: list[ApplianceConsumption]
    total_daily_energy_wh: float
    total_daily_energy_kwh: float
    simultaneous_power_w: float
    peak_starting_power_w: float
    day_energy_wh: float
    night_energy_wh: float
    essential_energy_wh: float
    optional_energy_wh: float
    uncertainty_margin: float
    growth_margin: float
    adjusted_daily_energy_wh: float
    warnings: list[str]


@dataclass(frozen=True)
class SizingResult:
    peak_sun_hours: float
    required_pv_power_w: float
    panel_count: int
    panel_power_w: float
    pv_total_power_w: float
    battery_count: int
    battery_capacity_ah: float
    battery_voltage_v: float
    battery_total_capacity_wh: float
    battery_usable_capacity_wh: float
    autonomy_hours_estimated: float
    inverter_power_w: float
    inverter_surge_power_w: float
    controller_current_a: float
    system_voltage_v: float
    safety_margin: float


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: str
    request: AdvisorRequest
    consumption: ConsumptionProfile
    sizing: SizingResult
    selected_components: dict[str, Any]
    alternatives: list[dict[str, Any]]
    explanation: list[str]
    quote: dict[str, Any]
    missing_information: list[str]
    assumptions: list[str]
    limitations: list[str]
    integration_links: dict[str, Any]
