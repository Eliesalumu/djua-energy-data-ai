from __future__ import annotations

import re
from typing import Any

from djua_energy.solar_advisor.schemas import AdvisorRequest, ApplianceNeed


FRENCH_NUMBERS = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "quinze": 15,
    "vingt": 20,
}

# Mapping: pattern -> (appliance_id, canonical_name, default_hours, default_power)
APPLIANCE_PATTERNS = [
    (r"\b(?:t[eé]l[eé]vision|t[eé]l[eé]|tv|t[eé]t[eé])\b", "television_led_32", "Télévision LED", 5, 45),
    (r"\b(?:cong[eé]lateur|freezer)\b", "freezer_small", "Congélateur économe", 24, 85),
    (r"\b(?:r[eé]frig[eé]rateur|frigo)\b", "fridge_efficient", "Réfrigérateur économe", 24, 75),
    (r"\b(?:ampoules?|lampes?|[eé]clairage|spots?)\b", "led_bulb_9w", "Ampoule LED", 6, 9),
    (r"\b(?:ventilateurs?|ventilos?)\b", "fan_table", "Ventilateur", 8, 40),
    (r"\b(?:t[eé]l[eé]phones?|smartphones?|chargeurs?)\b", "phone_charger", "Chargeur téléphone", 3, 15),
    (r"\b(?:ordinateurs?|laptops?|pc)\b", "laptop", "Ordinateur portable", 6, 65),
    (r"\b(?:routeurs?|box|wifi|modem)\b", "router", "Routeur Wifi", 12, 12),
    (r"\b(?:pompes?|pompage)\b", "water_pump_small", "Pompe à eau solaire", 4, 350),
    (r"\b(?:clim|climatiseurs?)\b", "air_conditioner_small", "Climatiseur Inverter", 6, 900),
    (r"\b(?:fers?\s*[aà]\s*repasser|fers?)\b", "iron", "Fer à repasser", 1, 1000),
    (r"\b(?:tondeuses?)\b", "hair_clipper", "Tondeuse de coiffure", 5, 25),
]

KNOWN_CITIES = [
    "kinshasa", "lubumbashi", "goma", "dakar", "abidjan", "brazzaville", 
    "matadi", "mbandaka", "yaounde", "yaoundé", "douala", "bamako", "lome", "lomé", "cotonou", "ouagadougou"
]


class ConversationEngine:
    def extract(self, message: str, context: dict[str, Any] | None = None) -> AdvisorRequest:
        context = context or {}
        existing_appliances = list(context.get("appliances", []))
        text = message.lower().strip()

        # Extract appliances from message
        extracted_map: dict[str, dict[str, Any]] = {}
        for item in existing_appliances:
            item_dict = item if isinstance(item, dict) else item.__dict__
            app_id = item_dict.get("appliance_id") or item_dict.get("name")
            if app_id:
                extracted_map[app_id] = dict(item_dict)

        for pattern, app_id, canonical_name, default_hours, default_power in APPLIANCE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                qty = self._extract_quantity_for_pattern(text, match.start(), match.end())
                hours = self._extract_hours_for_pattern(text, match.start(), match.end()) or default_hours
                
                # Check for capacity or details (e.g. 150 litres, 32 pouces)
                notes = ""
                liters_match = re.search(r"(\d+)\s*(?:l|litres?|litres)\b", text)
                if liters_match and ("frigo" in text or "congelateur" in text or "congélateur" in text):
                    notes = f"{liters_match.group(1)}L"
                inches_match = re.search(r"(\d+)\s*(?:pouces?|[\"'])\b", text)
                if inches_match and ("tv" in text or "télé" in text or "tele" in text or "tété" in text):
                    notes = f"{inches_match.group(1)}\""

                display_name = f"{canonical_name} {notes}".strip() if notes else canonical_name

                extracted_map[app_id] = {
                    "name": display_name,
                    "appliance_id": app_id,
                    "quantity": qty,
                    "hours_per_day": float(hours),
                    "power_w": float(default_power),
                    "usage_period": "night" if any(w in text for w in ["soir", "nuit", "nocturne"]) else "mixed",
                    "essential": True,
                }

        # Autonomy extraction
        autonomy = self._extract_autonomy(text) or context.get("autonomy_hours")

        # Budget extraction
        budget = self._extract_budget(text) or context.get("budget")

        # City extraction
        city = self._extract_city(text) or context.get("city") or "Kinshasa"

        appliances_list = list(extracted_map.values())

        request = AdvisorRequest(
            customer_id=context.get("customer_id") or f"prospect-{hash(message) & 0xfffffff}",
            city=city,
            region=context.get("region") or city.lower(),
            housing_type=context.get("housing_type", "household"),
            people_count=context.get("people_count", 5),
            autonomy_hours=float(autonomy) if autonomy else 10.0,
            budget=float(budget) if budget else None,
            preference=context.get("preference", "balanced"),
            appliances=[ApplianceNeed(**item) if isinstance(item, dict) else item for item in appliances_list],
            source="conversation",
            contact=context.get("contact", {}),
        )
        return request

    def next_questions(self, request: AdvisorRequest) -> list[str]:
        questions = []
        if not request.appliances:
            questions.append("Quels appareils électriques souhaitez-vous alimenter (ex: ampoules, TV, réfrigérateur...) ?")
        if request.autonomy_hours is None:
            questions.append("Combien d'heures d'autonomie souhaitez-vous la nuit ou en cas de coupure (ex: 8h, 12h) ?")
        if request.city is None and request.region is None:
            questions.append("Dans quelle ville ou localité le kit sera-t-il installé (ex: Kinshasa, Lubumbashi, Dakar...) ?")
        if request.budget is None:
            questions.append("Avez-vous un budget indicatif en XAF pour orienter la gamme de matériel ?")
        return questions[:3]

    def _extract_quantity_for_pattern(self, text: str, match_start: int, match_end: int) -> int:
        # Check window before pattern (up to 30 chars before)
        window_before = text[max(0, match_start - 30):match_start].strip()
        # Look for digits e.g. "8 ampoules", "1 congelateur"
        digit_match = re.search(r"(\d+)\s*(?:x|\*|\w+)?\s*$", window_before)
        if digit_match:
            return max(1, int(digit_match.group(1)))

        # Look for French words e.g. "une télé", "deux frigos", "huit ampoules"
        for word, val in FRENCH_NUMBERS.items():
            if re.search(rf"\b{re.escape(word)}\s*$", window_before):
                return val

        # Check right after pattern (e.g. "ampoules x 8", "tv: 1")
        window_after = text[match_end:min(len(text), match_end + 15)].strip()
        after_digit = re.search(r"^[:\s*x-]*(\d+)", window_after)
        if after_digit:
            return max(1, int(after_digit.group(1)))

        return 1

    def _extract_hours_for_pattern(self, text: str, match_start: int, match_end: int) -> float | None:
        window = text[match_start:min(len(text), match_end + 25)]
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|heures?|hrs?)\b", window)
        if match:
            return float(match.group(1).replace(",", "."))
        return None

    def _extract_autonomy(self, text: str) -> float | None:
        # e.g. "autonomie de 8 heures", "autonomie 10h", "8h d'autonomie", "8 heures par jour"
        match = re.search(r"(?:autonomie\s*(?:de)?\s*|pour\s*)(\d+(?:[.,]\d+)?)\s*(?:h|heures?|hrs?)", text)
        if match:
            return float(match.group(1).replace(",", "."))
        match_inv = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|heures?|hrs?)\s*(?:d['’]?autonomie|sans\s*soleil)", text)
        if match_inv:
            return float(match_inv.group(1).replace(",", "."))
        return None

    def _extract_budget(self, text: str) -> float | None:
        # e.g. "budget de 150 000", "budget 150000", "150 000 xaf", "150000 fcfa", "budget: 150.000"
        match = re.search(r"(?:budget\s*(?:de|est\s*de|:\s*)?)\s*(\d[\d\s.,]*\d|\d+)", text)
        if match:
            clean_str = match.group(1).replace(" ", "").replace(".", "").replace(",", ".")
            try:
                val = float(clean_str)
                if val >= 1000:
                    return val
            except ValueError:
                pass
        match_curr = re.search(r"(\d[\d\s.,]*\d|\d+)\s*(?:xaf|fcfa|cfa|francs?)", text)
        if match_curr:
            clean_str = match_curr.group(1).replace(" ", "").replace(".", "").replace(",", ".")
            try:
                val = float(clean_str)
                if val >= 1000:
                    return val
            except ValueError:
                pass
        return None

    def _extract_city(self, text: str) -> str | None:
        for city in KNOWN_CITIES:
            if re.search(rf"\b{re.escape(city)}\b", text):
                return city.capitalize()
        # Look for pattern "à [Ville]" or "a [Ville]"
        match = re.search(r"\b(?:[aà]|ville\s*de)\s+([A-Z][a-z]+)\b", text)
        if match:
            return match.group(1).capitalize()
        return None
