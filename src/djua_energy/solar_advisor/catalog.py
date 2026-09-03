from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from djua_energy.solar_advisor.schemas import ApplianceCatalogItem, Component


DEFAULT_CATALOG_DIR = Path("data/catalogs")


def _float(value: str | None, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    return float(value)


class ApplianceCatalog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_CATALOG_DIR / "appliances.csv")
        self.items = self._load()

    def _load(self) -> list[ApplianceCatalogItem]:
        with self.path.open(encoding="utf-8", newline="") as handle:
            return [
                ApplianceCatalogItem(
                    appliance_id=row["appliance_id"],
                    category=row["category"],
                    name=row["name"],
                    common_name_fr=row["common_name_fr"],
                    typical_power_w=_float(row.get("typical_power_w")),
                    standby_power_w=_float(row.get("standby_power_w")),
                    starting_power_w=_float(row.get("starting_power_w")),
                    surge_multiplier=_float(row.get("surge_multiplier"), 1.0),
                    average_daily_hours=_float(row.get("average_daily_hours"), 1.0),
                    duty_cycle=_float(row.get("duty_cycle"), 1.0),
                    min_power_w=_float(row.get("min_power_w")),
                    max_power_w=_float(row.get("max_power_w")),
                    confidence_level=row.get("confidence_level", "medium"),
                    notes=row.get("notes", ""),
                )
                for row in csv.DictReader(handle)
            ]

    def find(self, name: str | None = None, appliance_id: str | None = None) -> ApplianceCatalogItem | None:
        if appliance_id:
            for item in self.items:
                if item.appliance_id == appliance_id:
                    return item
        if not name:
            return None
        query = _normalize(name)
        for item in self.items:
            aliases = [item.name, item.common_name_fr, item.category]
            if any(query in _normalize(alias) or _normalize(alias) in query for alias in aliases):
                return item
        return None

    def search(self, query: str) -> list[ApplianceCatalogItem]:
        normalized = _normalize(query)
        return [
            item
            for item in self.items
            if normalized in _normalize(item.name)
            or normalized in _normalize(item.common_name_fr)
            or normalized in _normalize(item.category)
        ]


class ComponentCatalog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_CATALOG_DIR / "solar_components.csv")
        self.components = self._load()

    def _load(self) -> list[Component]:
        with self.path.open(encoding="utf-8", newline="") as handle:
            return [
                Component(
                    component_id=row["component_id"],
                    component_type=row["component_type"],
                    manufacturer=row["manufacturer"],
                    model=row["model"],
                    nominal_power_w=_float(row.get("nominal_power_w")),
                    capacity_ah=_float(row.get("capacity_ah")),
                    capacity_wh=_float(row.get("capacity_wh")),
                    voltage_v=_float(row.get("voltage_v")),
                    chemistry=row.get("chemistry", ""),
                    usable_depth_of_discharge=_float(row.get("usable_depth_of_discharge")),
                    efficiency=_float(row.get("efficiency"), 1.0),
                    inverter_continuous_power_w=_float(row.get("inverter_continuous_power_w")),
                    inverter_surge_power_w=_float(row.get("inverter_surge_power_w")),
                    controller_type=row.get("controller_type", ""),
                    controller_current_a=_float(row.get("controller_current_a")),
                    unit_price=_float(row.get("unit_price")),
                    currency=row.get("currency", "XAF"),
                    stock_status=row.get("stock_status", "demo"),
                    compatible_system_voltage=row.get("compatible_system_voltage", ""),
                    is_synthetic=str(row.get("is_synthetic", "true")).lower() == "true",
                )
                for row in csv.DictReader(handle)
                if str(row.get("active", "true")).lower() == "true"
            ]

    def by_type(self, component_type: str) -> list[Component]:
        return [item for item in self.components if item.component_type == component_type]

    def smallest_panel_at_least(self, required_power_w: float) -> Component:
        panels = sorted(self.by_type("panel"), key=lambda item: item.nominal_power_w)
        return min(panels, key=lambda panel: abs(panel.nominal_power_w - min(max(required_power_w, 120), 550)))

    def choose_inverter(self, continuous_power_w: float, surge_power_w: float) -> Component:
        inverters = sorted(self.by_type("inverter"), key=lambda item: item.inverter_continuous_power_w)
        for item in inverters:
            if item.inverter_continuous_power_w >= continuous_power_w and item.inverter_surge_power_w >= surge_power_w:
                return item
        return inverters[-1]

    def choose_controller(self, current_a: float) -> Component:
        controllers = sorted(self.by_type("controller"), key=lambda item: item.controller_current_a)
        for item in controllers:
            if item.controller_current_a >= current_a:
                return item
        return controllers[-1]

    def choose_battery(self, required_wh: float, system_voltage_v: float, preference: str) -> Component:
        batteries = sorted(self.by_type("battery"), key=lambda item: item.capacity_wh)
        if preference == "economy":
            preferred = [item for item in batteries if item.chemistry.lower().startswith("agm")]
            batteries = preferred or batteries
        else:
            preferred = [item for item in batteries if "lifepo" in item.chemistry.lower()]
            batteries = preferred or batteries
        for item in batteries:
            usable = max(item.capacity_wh, item.capacity_ah * item.voltage_v) * max(item.usable_depth_of_discharge, 0.5)
            count = max(1, int(-(-required_wh // max(usable, 1))))
            if item.voltage_v * count >= system_voltage_v or count >= 2:
                return item
        return batteries[-1]


def public_rows(items: Iterable[object]) -> list[dict]:
    rows = []
    for item in items:
        rows.append(dict(item.__dict__))
    return rows


def _normalize(value: str) -> str:
    return value.lower().replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a").replace("ô", "o")
