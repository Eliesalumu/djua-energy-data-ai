from __future__ import annotations

from datetime import UTC, datetime


class QuoteService:
    def build_quote(self, recommendation_id: str, selected_components: dict, counts: dict) -> dict:
        items = []
        total = 0.0
        for key, component in selected_components.items():
            quantity = int(counts.get(key, 1))
            unit_price = float(component.get("unit_price", 0))
            line_total = quantity * unit_price
            total += line_total
            items.append(
                {
                    "item_type": key,
                    "component_id": component.get("component_id"),
                    "label": f"{component.get('manufacturer')} {component.get('model')}",
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": round(line_total, 2),
                    "currency": component.get("currency", "XAF"),
                    "is_synthetic_price": component.get("is_synthetic", True),
                }
            )
        return {
            "quote_id": f"quote-{recommendation_id}",
            "recommendation_id": recommendation_id,
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "currency": items[0]["currency"] if items else "XAF",
            "total_estimated": round(total, 2),
            "items": items,
            "pricing_notice": "Prix de demonstration synthetiques: remplacer par le catalogue commercial officiel Orange Energy.",
        }
