from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from typing import Any, Protocol

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
AMBIGUOUS = "ambiguous"
CONFLICT = "conflict"
STALE = "stale"

def parse_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return datetime.fromtimestamp(float(raw), tz=UTC)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None

@dataclass(frozen=True)
class CustomerKitAssignment:
    assignment_id: str
    client_id: str
    kit_id: str
    device_id: str
    contract_id: str
    valid_from: str
    valid_to: str | None = None
    status: str = "active"
    source: str = "backend"
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class IdentityResolution:
    status: str
    confidence: float
    method: str
    source: str
    identity: dict[str, Any]
    reason_codes: list[str]
    assignment: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class AssignmentRepository(Protocol):
    def resolve_assignment(
        self,
        *,
        device_id: str | None,
        kit_id: str | None,
        event_time: str | None,
    ) -> list[dict[str, Any]]:
        ...

class IdentityResolver:
    def __init__(self, repository: AssignmentRepository | None = None) -> None:
        self.repository = repository

    def resolve(
        self,
        *,
        provided_identity: dict[str, Any] | None,
        event_time: str | None,
    ) -> IdentityResolution:
        identity = dict(provided_identity or {})
        device_id = identity.get("device_id")
        kit_id = identity.get("kit_id")

        if not device_id and not kit_id:
            return IdentityResolution(
                status=UNRESOLVED,
                confidence=0.0,
                method="provided_identity",
                source="request",
                identity=identity,
                reason_codes=["IDENTITY_UNRESOLVED"],
            )

        matches = []
        if self.repository is not None:
            matches = self.repository.resolve_assignment(
                device_id=device_id,
                kit_id=kit_id,
                event_time=event_time,
            )

        if len(matches) > 1:
            return IdentityResolution(
                status=AMBIGUOUS,
                confidence=0.0,
                method="assignment_history",
                source="customer_kit_assignments",
                identity=identity,
                reason_codes=["IDENTITY_AMBIGUOUS"],
            )

        if len(matches) == 1:
            assignment = matches[0]
            conflict_fields = [
                field
                for field in ["client_id", "kit_id", "device_id", "contract_id", "assignment_id"]
                if identity.get(field) and assignment.get(field) and identity[field] != assignment[field]
            ]
            if conflict_fields:
                return IdentityResolution(
                    status=CONFLICT,
                    confidence=0.0,
                    method="assignment_history",
                    source="customer_kit_assignments",
                    identity={**identity, "conflict_fields": conflict_fields},
                    assignment=assignment,
                    reason_codes=["IDENTITY_CONFLICT"],
                )

            resolved = {
                "client_id": assignment.get("client_id"),
                "kit_id": assignment.get("kit_id"),
                "device_id": assignment.get("device_id"),
                "contract_id": assignment.get("contract_id"),
                "assignment_id": assignment.get("assignment_id"),
                "resolution_status": RESOLVED,
            }
            return IdentityResolution(
                status=RESOLVED,
                confidence=1.0,
                method="assignment_history",
                source="customer_kit_assignments",
                identity=resolved,
                assignment=assignment,
                reason_codes=[],
            )

        has_full_identity = all(identity.get(field) for field in ["client_id", "kit_id", "device_id", "contract_id", "assignment_id"])
        if has_full_identity:
            identity["resolution_status"] = RESOLVED
            return IdentityResolution(
                status=RESOLVED,
                confidence=0.75,
                method="provided_identity",
                source="request",
                identity=identity,
                reason_codes=["IDENTITY_PROVIDED_NOT_VERIFIED"],
            )

        identity["resolution_status"] = UNRESOLVED
        return IdentityResolution(
            status=UNRESOLVED,
            confidence=0.0,
            method="assignment_history",
            source="customer_kit_assignments",
            identity=identity,
            reason_codes=["IDENTITY_UNRESOLVED"],
        )

