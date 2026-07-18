"""Validation helpers for incoming telemetry records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from djua_energy.pipeline.contracts import validate_payload


@dataclass(frozen=True)
class RecordValidation:
    record: dict[str, Any]
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_record(record: dict[str, Any]) -> RecordValidation:
    result = validate_payload(record)
    return RecordValidation(
        record=record,
        valid=bool(result["valid"]),
        errors=list(result.get("errors", [])),
    )


def validate_records(records: list[dict[str, Any]]) -> list[RecordValidation]:
    return [validate_record(record) for record in records]


def split_valid_invalid(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[RecordValidation]]:
    validations = validate_records(records)
    valid_records = [item.record for item in validations if item.valid]
    invalid_records = [item for item in validations if not item.valid]
    return valid_records, invalid_records
