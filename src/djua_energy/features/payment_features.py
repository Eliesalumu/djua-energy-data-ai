from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


SUCCESS_STATUSES = {"paid", "completed", "success", "successful", "settled"}
LATE_STATUSES = {"late"}
MISSED_STATUSES = {"missed", "pending", "overdue", "unpaid"}
FAILED_STATUSES = {"failed", "rejected", "cancelled", "canceled"}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return datetime.fromtimestamp(float(raw), tz=UTC)
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _number(payload: dict[str, Any], *names: str) -> float:
    for name in names:
        value = payload.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _payment_date(payment: dict[str, Any]) -> datetime | None:
    # Plusieurs backends nomment differemment la date; on normalise sans imposer un seul champ.
    return (
        _parse_datetime(payment.get("paid_at"))
        or _parse_datetime(payment.get("date"))
        or _parse_datetime(payment.get("payment_date"))
        or _parse_datetime(payment.get("created_at"))
        or _parse_datetime(payment.get("due_date"))
    )


def _days_late(payment: dict[str, Any]) -> float:
    # Priorite au retard explicite; sinon on le deduit de due_date et paid_at.
    explicit = payment.get("days_late")
    if explicit not in (None, ""):
        try:
            return max(0.0, float(explicit))
        except (TypeError, ValueError):
            pass
    due_date = _parse_datetime(payment.get("due_date"))
    paid_at = _parse_datetime(payment.get("paid_at")) or _parse_datetime(payment.get("date"))
    if due_date and paid_at:
        return max(0.0, float((paid_at - due_date).days))
    return 0.0


def build_payment_features(payments: list[dict[str, Any]], *, as_of: str | None = None) -> dict[str, Any]:
    # Transforme l'historique brut Orange/backend en signaux de risque paiement sur 6 mois.
    reference_time = _parse_datetime(as_of) or datetime.now(tz=UTC)
    window_start = reference_time - timedelta(days=183)
    window_payments = [
        payment for payment in payments
        if (payment_date := _payment_date(payment)) is not None and payment_date >= window_start
    ]
    if not window_payments:
        return {}

    statuses = [str(payment.get("status") or "").lower() for payment in window_payments]
    successful = [payment for payment, status in zip(window_payments, statuses) if status in SUCCESS_STATUSES]
    late = [
        payment for payment, status in zip(window_payments, statuses)
        if status in LATE_STATUSES or _days_late(payment) > 0
    ]
    missed = [payment for payment, status in zip(window_payments, statuses) if status in MISSED_STATUSES]
    failed = [payment for payment, status in zip(window_payments, statuses) if status in FAILED_STATUSES]

    paid_dates = [_payment_date(payment) for payment in successful]
    paid_dates = [date for date in paid_dates if date is not None]
    last_payment_date = max(paid_dates) if paid_dates else None
    last_known_payment = max(window_payments, key=lambda payment: _payment_date(payment) or window_start)
    late_days = [_days_late(payment) for payment in late]

    outstanding_balance = 0.0
    for payment, status in zip(window_payments, statuses):
        amount_due = _number(payment, "amount_due", "amountDue", "amountUSD", "amount_usd")
        amount_paid = _number(payment, "amount_paid", "amountPaid")
        if status in MISSED_STATUSES | FAILED_STATUSES:
            outstanding_balance += max(0.0, amount_due - amount_paid)

    return {
        "payments_last_6_months": len(window_payments),
        "late_payments_last_6_months": len(late),
        "missed_payments_last_6_months": len(missed),
        "failed_payments_last_6_months": len(failed),
        "payment_success_rate": round(len(successful) / len(window_payments), 4),
        "average_days_late": round(sum(late_days) / len(late_days), 2) if late_days else 0.0,
        "outstanding_balance": round(outstanding_balance, 2),
        "days_since_last_payment": (reference_time - last_payment_date).days if last_payment_date else None,
        "last_payment_status": str(last_known_payment.get("status") or "unknown").lower(),
        "source": "computed_from_raw_payments",
    }
