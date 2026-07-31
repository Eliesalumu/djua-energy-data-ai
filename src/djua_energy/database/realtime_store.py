from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


DEFAULT_DATABASE_PATH = Path("data/runtime/djua_realtime.sqlite")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _database_path_from_env() -> Path:
    url = os.getenv("DJUA_DATABASE_URL")
    if not url:
        return DEFAULT_DATABASE_PATH
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    if url.startswith("sqlite://"):
        return Path(url.replace("sqlite://", "", 1))
    raise ValueError(
        "DJUA_DATABASE_URL doit etre une URL sqlite pour ce MVP, "
        "exemple: sqlite:///data/runtime/djua_realtime.sqlite"
    )


class RealtimeTelemetryStore:
    """Persistent storage for live telemetry, predictions and device state."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path else _database_path_from_env()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_records (
                    message_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    kit_id TEXT,
                    event_time TEXT NOT NULL,
                    sequence_number INTEGER,
                    scenario TEXT,
                    payload_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
                    ON telemetry_records(device_id, event_time);

                CREATE TABLE IF NOT EXISTS prediction_history (
                    prediction_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    kit_id TEXT,
                    predicted_at TEXT NOT NULL,
                    window_started_at TEXT,
                    window_ended_at TEXT,
                    records_used INTEGER NOT NULL,
                    maintenance_probability REAL NOT NULL,
                    security_probability REAL NOT NULL,
                    risk_score INTEGER NOT NULL,
                    risk_level TEXT NOT NULL,
                    alert_priority TEXT NOT NULL,
                    recommended_action TEXT,
                    maintenance_prediction_json TEXT NOT NULL,
                    security_prediction_json TEXT NOT NULL,
                    alert_json TEXT NOT NULL,
                    feature_snapshot_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_predictions_device_time
                    ON prediction_history(device_id, predicted_at);

                CREATE TABLE IF NOT EXISTS device_state (
                    device_id TEXT PRIMARY KEY,
                    kit_id TEXT,
                    last_event_time TEXT NOT NULL,
                    last_prediction_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    risk_score INTEGER NOT NULL,
                    alert_priority TEXT NOT NULL,
                    recommended_action TEXT,
                    latest_payload_json TEXT NOT NULL,
                    latest_prediction_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def insert_telemetry_records(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        new_records: list[dict[str, Any]] = []
        duplicate_records: list[dict[str, Any]] = []
        inserted_at = _now_iso()
        with self._connect() as connection:
            for record in records:
                message_id = str(record.get("message_id", ""))
                try:
                    connection.execute(
                        """
                        INSERT INTO telemetry_records (
                            message_id, device_id, kit_id, event_time, sequence_number,
                            scenario, payload_json, inserted_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            message_id,
                            str(record.get("device_id", "unknown")),
                            record.get("kit_id"),
                            str(record.get("event_time", inserted_at)),
                            record.get("sequence_number"),
                            record.get("scenario"),
                            json.dumps(record, ensure_ascii=False, sort_keys=True),
                            inserted_at,
                        ),
                    )
                    new_records.append(record)
                except sqlite3.IntegrityError:
                    duplicate_records.append(record)
        return new_records, duplicate_records

    def recent_records_for_device(self, device_id: str, *, limit: int = 24) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM telemetry_records
                WHERE device_id = ?
                ORDER BY CAST(event_time AS INTEGER) DESC, event_time DESC, inserted_at DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        records = [json.loads(row["payload_json"]) for row in rows]
        records.reverse()
        return records

    def save_prediction(
        self,
        *,
        device_id: str,
        kit_id: str | None,
        window_records: list[dict[str, Any]],
        maintenance_prediction: dict[str, Any],
        security_prediction: dict[str, Any],
        alert: dict[str, Any],
        feature_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        predicted_at = _now_iso()
        maintenance_probability = float(maintenance_prediction["technical_risk_probability"])
        security_probability = float(security_prediction["suspicious_activity_score"])
        risk_score = round(max(maintenance_probability, security_probability) * 100)
        alert_priority = str(alert.get("priority", "none"))
        risk_level = "low" if alert_priority == "none" else alert_priority
        latest = window_records[-1]
        status = "offline" if latest.get("connection_status") == "disconnected" else "operational"
        prediction_id = f"{device_id}-{predicted_at}-{latest.get('message_id', len(window_records))}"
        prediction_payload = {
            "prediction_id": prediction_id,
            "device_id": device_id,
            "kit_id": kit_id,
            "predicted_at": predicted_at,
            "window_started_at": str(window_records[0].get("event_time")),
            "window_ended_at": str(window_records[-1].get("event_time")),
            "records_used": len(window_records),
            "maintenance_probability": maintenance_probability,
            "security_probability": security_probability,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "alert_priority": alert_priority,
            "recommended_action": alert.get("recommended_action"),
            "maintenance_prediction": maintenance_prediction,
            "security_prediction": security_prediction,
            "alert": alert,
            "feature_snapshot": feature_snapshot,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO prediction_history (
                    prediction_id, device_id, kit_id, predicted_at, window_started_at,
                    window_ended_at, records_used, maintenance_probability,
                    security_probability, risk_score, risk_level, alert_priority,
                    recommended_action, maintenance_prediction_json, security_prediction_json,
                    alert_json, feature_snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction_id,
                    device_id,
                    kit_id,
                    predicted_at,
                    prediction_payload["window_started_at"],
                    prediction_payload["window_ended_at"],
                    len(window_records),
                    maintenance_probability,
                    security_probability,
                    risk_score,
                    risk_level,
                    alert_priority,
                    alert.get("recommended_action"),
                    json.dumps(maintenance_prediction, ensure_ascii=False, sort_keys=True),
                    json.dumps(security_prediction, ensure_ascii=False, sort_keys=True),
                    json.dumps(alert, ensure_ascii=False, sort_keys=True),
                    json.dumps(feature_snapshot, ensure_ascii=False, sort_keys=True),
                ),
            )
            connection.execute(
                """
                INSERT INTO device_state (
                    device_id, kit_id, last_event_time, last_prediction_at, status,
                    risk_level, risk_score, alert_priority, recommended_action,
                    latest_payload_json, latest_prediction_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    kit_id = excluded.kit_id,
                    last_event_time = excluded.last_event_time,
                    last_prediction_at = excluded.last_prediction_at,
                    status = excluded.status,
                    risk_level = excluded.risk_level,
                    risk_score = excluded.risk_score,
                    alert_priority = excluded.alert_priority,
                    recommended_action = excluded.recommended_action,
                    latest_payload_json = excluded.latest_payload_json,
                    latest_prediction_json = excluded.latest_prediction_json,
                    updated_at = excluded.updated_at
                """,
                (
                    device_id,
                    kit_id,
                    str(latest.get("event_time")),
                    predicted_at,
                    status,
                    risk_level,
                    risk_score,
                    alert_priority,
                    alert.get("recommended_action"),
                    json.dumps(latest, ensure_ascii=False, sort_keys=True),
                    json.dumps(prediction_payload, ensure_ascii=False, sort_keys=True),
                    predicted_at,
                ),
            )
        return prediction_payload

    def list_device_states(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM device_state
                ORDER BY risk_score DESC, last_event_time DESC
                """
            ).fetchall()
        return [self._state_from_row(row) for row in rows]

    def get_device_state(self, device_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM device_state WHERE device_id = ?", (device_id,)).fetchone()
        return self._state_from_row(row) if row else None

    def prediction_history(self, device_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM prediction_history
                WHERE device_id = ?
                ORDER BY predicted_at DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [self._prediction_from_row(row) for row in rows]

    def _state_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        state = dict(row)
        state["latest_payload"] = json.loads(state.pop("latest_payload_json"))
        state["latest_prediction"] = json.loads(state.pop("latest_prediction_json"))
        return state

    def _prediction_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        prediction = dict(row)
        prediction["maintenance_prediction"] = json.loads(prediction.pop("maintenance_prediction_json"))
        prediction["security_prediction"] = json.loads(prediction.pop("security_prediction_json"))
        prediction["alert"] = json.loads(prediction.pop("alert_json"))
        prediction["feature_snapshot"] = json.loads(prediction.pop("feature_snapshot_json"))
        return prediction
