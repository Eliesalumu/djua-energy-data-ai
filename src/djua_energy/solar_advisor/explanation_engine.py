from __future__ import annotations

from djua_energy.solar_advisor.schemas import AdvisorRequest, ConsumptionProfile, SizingResult


class ExplanationEngine:
    def explain(self, request: AdvisorRequest, consumption: ConsumptionProfile, sizing: SizingResult) -> list[str]:
        city = request.city or request.region or "la zone indiquee"
        return [
            f"La consommation estimee est de {consumption.total_daily_energy_kwh} kWh par jour avant marges.",
            f"Une marge totale de {int(sizing.safety_margin * 100)}% couvre les incertitudes et l'evolution future.",
            f"Avec environ {sizing.peak_sun_hours} heures solaires utiles a {city}, il faut environ {sizing.required_pv_power_w:.0f} Wc de panneaux.",
            f"La recommandation installe {sizing.panel_count} panneau(x) de {sizing.panel_power_w:.0f} W, soit {sizing.pv_total_power_w:.0f} Wc.",
            f"Le banc batterie utile couvre environ {sizing.autonomy_hours_estimated:.1f} heures selon les usages declares.",
            f"L'onduleur de {sizing.inverter_power_w:.0f} W garde une reserve pour les demarrages d'appareils.",
        ]
