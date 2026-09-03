"""Telemetry ingestion orchestration for the local MVP."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from djua_energy.alerting.service import AlertDecision, build_alert_decision
from djua_energy.database.realtime_store import RealtimeTelemetryStore
from djua_energy.ingestion.idempotency import InMemoryIdempotencyStore
from djua_energy.ingestion.quarantine import InMemoryQuarantineStore
from djua_energy.ingestion.validation import split_valid_invalid_prediction
from djua_energy.kit_intelligence.service import build_kit_intelligence
from djua_energy.observability.audit import InMemoryAuditLog
from djua_energy.observability.metrics import InMemoryMetrics
from djua_energy.pipeline.features import build_maintenance_features, build_security_features
from djua_energy.pipeline.inference import LocalInferenceEngine


class TelemetryIngestionService:
    def __init__(
        self,
        inference_engine: LocalInferenceEngine,
        idempotency_store: InMemoryIdempotencyStore | None = None,
        quarantine_store: InMemoryQuarantineStore | None = None,
        audit_log: InMemoryAuditLog | None = None,
        metrics: InMemoryMetrics | None = None,
        realtime_store: RealtimeTelemetryStore | None = None,
        sliding_window_size: int = 24,
    ) -> None:
        self.inference_engine = inference_engine
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()
        self.quarantine_store = quarantine_store or InMemoryQuarantineStore()
        self.audit_log = audit_log or InMemoryAuditLog()
        self.metrics = metrics or InMemoryMetrics()
        self.realtime_store = realtime_store
        self.sliding_window_size = sliding_window_size

    def process_window(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            raise ValueError("records cannot be empty")

        self.metrics.increment("ingestion.windows_received")
        self.metrics.increment("ingestion.records_received", len(records))

        valid_records, invalid_records = split_valid_invalid_prediction(records)
        for invalid in invalid_records:
            self.quarantine_store.add(invalid.record, invalid.errors)
        if invalid_records:
            self.metrics.increment("ingestion.records_quarantined", len(invalid_records))
            self.audit_log.record(
                "records_quarantined",
                details={"count": len(invalid_records), "errors": [item.errors for item in invalid_records]},
            )

        if self.realtime_store:
            new_records, duplicate_records = self.realtime_store.insert_telemetry_records(valid_records)
        else:
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
        window_records = self._records_for_prediction(device_id, new_records)
        maintenance_prediction = self.inference_engine.infer_maintenance(window_records)
        security_prediction = self.inference_engine.infer_security(window_records)
        alert_decision = build_alert_decision(
            device_id=device_id,
            maintenance_prediction=maintenance_prediction,
            security_prediction=security_prediction,
            kit_id=new_records[-1].get("kit_id"),
            event_time=str(new_records[-1].get("event_time")),
        )
        alert_payload = asdict(alert_decision)
        feature_snapshot = self._build_feature_snapshot(window_records)
        kit_intelligence = build_kit_intelligence(
            records=window_records,
            inference_engine=self.inference_engine,
            maintenance_prediction=maintenance_prediction,
            security_prediction=security_prediction,
        )
        stored_prediction = None
        if self.realtime_store:
            stored_prediction = self.realtime_store.save_prediction(
                device_id=device_id,
                kit_id=new_records[-1].get("kit_id"),
                window_records=window_records,
                maintenance_prediction=maintenance_prediction,
                security_prediction=security_prediction,
                alert=alert_payload,
                feature_snapshot=feature_snapshot,
            )

        self._record_alert_metrics(alert_decision)
        self.audit_log.record(
            "prediction_completed",
            device_id=device_id,
            details={
                "records_analyzed": len(window_records),
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
            "prediction_window_records": len(window_records),
            "quarantined_records": len(invalid_records),
            "duplicate_records": len(duplicate_records),
            "alert": alert_payload,
            "kit_intelligence": kit_intelligence,
            "feature_snapshot": feature_snapshot,
            "stored_prediction": stored_prediction,
            "metrics": self.metrics.snapshot(),
        }

    def _record_alert_metrics(self, alert_decision: AlertDecision) -> None:
        self.metrics.increment("predictions.completed")
        self.metrics.increment(f"alerts.priority.{alert_decision.priority}")
        if alert_decision.priority != "none":
            self.metrics.increment("alerts.created")

    def _records_for_prediction(self, device_id: str, new_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.realtime_store:
            return new_records[-self.sliding_window_size :]
        records = self.realtime_store.recent_records_for_device(device_id, limit=self.sliding_window_size)
        return records or new_records[-self.sliding_window_size :]

    def _build_feature_snapshot(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        maintenance_features = build_maintenance_features(records).iloc[-1].to_dict()
        security_features = build_security_features(records).iloc[-1].to_dict()
        return {
            "maintenance": {
                "battery_voltage_trend": round(float(maintenance_features.get("battery_voltage_trend", 0)), 3),
                "battery_temp_trend": round(float(maintenance_features.get("battery_temp_trend", 0)), 3),
                "max_battery_temp": round(float(maintenance_features.get("max_battery_temp", 0)), 3),
                "connectivity_gap": round(float(maintenance_features.get("connectivity_gap", 0)), 3),
                "solar_load_ratio": round(float(maintenance_features.get("solar_load_ratio", 0)), 3),
                "battery_age_months": round(float(maintenance_features.get("battery_age_months", 0)), 3),
            },
            "security": {
                "distance_to_installation": round(float(security_features.get("distance_to_installation", 0)), 3),
                "geofence_exit": round(float(security_features.get("geofence_exit", 0)), 3),
                "movement_then_gap": round(float(security_features.get("movement_then_gap", 0)), 3),
                "device_silence_duration": round(float(security_features.get("device_silence_duration", 0)), 3),
                "enclosure_opened": round(float(security_features.get("enclosure_opened", 0)), 3),
                "tamper_events": round(float(security_features.get("tamper_events", 0)), 3),
            },
        }
