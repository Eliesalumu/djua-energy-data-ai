"""Telemetry ingestion orchestration for the local MVP."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from djua_energy.alerting.service import AlertDecision, build_alert_decision
from djua_energy.ingestion.idempotency import InMemoryIdempotencyStore
from djua_energy.ingestion.quarantine import InMemoryQuarantineStore
from djua_energy.ingestion.validation import split_valid_invalid
from djua_energy.observability.audit import InMemoryAuditLog
from djua_energy.observability.metrics import InMemoryMetrics
from djua_energy.pipeline.inference import LocalInferenceEngine


class TelemetryIngestionService:
    def __init__(
        self,
        inference_engine: LocalInferenceEngine,
        idempotency_store: InMemoryIdempotencyStore | None = None,
        quarantine_store: InMemoryQuarantineStore | None = None,
        audit_log: InMemoryAuditLog | None = None,
        metrics: InMemoryMetrics | None = None,
    ) -> None:
        self.inference_engine = inference_engine
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()
        self.quarantine_store = quarantine_store or InMemoryQuarantineStore()
        self.audit_log = audit_log or InMemoryAuditLog()
        self.metrics = metrics or InMemoryMetrics()

    def process_window(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            raise ValueError("records cannot be empty")

        self.metrics.increment("ingestion.windows_received")
        self.metrics.increment("ingestion.records_received", len(records))

        valid_records, invalid_records = split_valid_invalid(records)
        for invalid in invalid_records:
            self.quarantine_store.add(invalid.record, invalid.errors)
        if invalid_records:
            self.metrics.increment("ingestion.records_quarantined", len(invalid_records))
            self.audit_log.record(
                "records_quarantined",
                details={"count": len(invalid_records), "errors": [item.errors for item in invalid_records]},
            )

        new_records, duplicate_records = self.idempotency_store.filter_new(valid_records)
        if duplicate_records:
            self.metrics.increment("ingestion.duplicates_ignored", len(duplicate_records))
            self.audit_log.record("duplicates_ignored", details={"count": len(duplicate_records)})

        if not new_records:
            self.metrics.increment("ingestion.windows_without_new_records")
            return {
                "status": "no_new_records",
                "valid_records": len(valid_records),
                "quarantined_records": len(invalid_records),
                "duplicate_records": len(duplicate_records),
                "alert": None,
                "metrics": self.metrics.snapshot(),
            }

        device_id = str(new_records[-1].get("device_id", "unknown"))
        maintenance_prediction = self.inference_engine.infer_maintenance(new_records)
        security_prediction = self.inference_engine.infer_security(new_records)
        alert_decision = build_alert_decision(
            device_id=device_id,
            maintenance_prediction=maintenance_prediction,
            security_prediction=security_prediction,
        )

        self._record_alert_metrics(alert_decision)
        self.audit_log.record(
            "prediction_completed",
            device_id=device_id,
            details={
                "records_analyzed": len(new_records),
                "priority": alert_decision.priority,
                "maintenance_priority": alert_decision.maintenance_priority,
                "security_priority": alert_decision.security_priority,
            },
        )

        return {
            "status": "processed",
            "device_id": device_id,
            "records_received": len(records),
            "records_analyzed": len(new_records),
            "quarantined_records": len(invalid_records),
            "duplicate_records": len(duplicate_records),
            "alert": asdict(alert_decision),
            "metrics": self.metrics.snapshot(),
        }

    def _record_alert_metrics(self, alert_decision: AlertDecision) -> None:
        self.metrics.increment("predictions.completed")
        self.metrics.increment(f"alerts.priority.{alert_decision.priority}")
        if alert_decision.priority != "none":
            self.metrics.increment("alerts.created")
