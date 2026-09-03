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
            # Read model local IA/Data: historique brut, predictions, etats courants, clients, decisions.
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_records (
                    message_id TEXT PRIMARY KEY,
                    client_id TEXT,
                    device_id TEXT NOT NULL,
                    kit_id TEXT,
                    contract_id TEXT,
                    assignment_id TEXT,
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
                    client_id TEXT,
                    device_id TEXT NOT NULL,
                    kit_id TEXT,
                    contract_id TEXT,
                    assignment_id TEXT,
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
                    client_id TEXT,
                    contract_id TEXT,
                    assignment_id TEXT,
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

                CREATE TABLE IF NOT EXISTS customers (
                    client_id TEXT PRIMARY KEY,
                    latest_kit_id TEXT,
                    latest_device_id TEXT,
                    latest_contract_id TEXT,
                    latest_assignment_id TEXT,
                    customer_segment TEXT,
                    tenure_months REAL,
                    active_contracts INTEGER,
                    latest_client_value_score INTEGER,
                    latest_payment_risk_score INTEGER,
                    latest_operational_risk_score INTEGER,
                    latest_intervention_priority_score INTEGER,
                    latest_decision_id TEXT,
                    latest_decision_at TEXT,
                    raw_customer_json TEXT NOT NULL,
                    raw_identity_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS customer_decision_history (
                    decision_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    client_id TEXT,
                    kit_id TEXT,
                    device_id TEXT,
                    contract_id TEXT,
                    assignment_id TEXT,
                    as_of TEXT,
                    identity_status TEXT NOT NULL,
                    client_value_score INTEGER,
                    payment_risk_score INTEGER,
                    operational_risk_score INTEGER,
                    intervention_priority_score INTEGER,
                    recommended_action TEXT,
                    priority TEXT,
                    confidence REAL,
                    input_snapshot_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_customer_decisions_client_time
                    ON customer_decision_history(client_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_customer_decisions_kit_time
                    ON customer_decision_history(kit_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_customer_decisions_priority_time
                    ON customer_decision_history(priority, created_at);

                """
            )
            self._ensure_columns(
                connection,
                "telemetry_records",
                {
                    "client_id": "TEXT",
                    "contract_id": "TEXT",
                    "assignment_id": "TEXT",
                },
            )
            self._ensure_columns(
                connection,
                "prediction_history",
                {
                    "client_id": "TEXT",
                    "contract_id": "TEXT",
                    "assignment_id": "TEXT",
                },
            )
            self._ensure_columns(
                connection,
                "device_state",
                {
                    "client_id": "TEXT",
                    "contract_id": "TEXT",
                    "assignment_id": "TEXT",
                },
            )
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_telemetry_client_time
                    ON telemetry_records(client_id, event_time);

                CREATE INDEX IF NOT EXISTS idx_predictions_client_time
                    ON prediction_history(client_id, predicted_at);
                """
            )

    def _ensure_columns(self, connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        # Migration douce pour les bases SQLite deja creees avant l'ajout des champs client.
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def insert_telemetry_records(
        self,
        records: list[dict[str, Any]],
        *,
        identity: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # Les mesures restent brutes, mais on y copie l'identite backend pour les recherches client/kit.
        new_records: list[dict[str, Any]] = []
        duplicate_records: list[dict[str, Any]] = []
        inserted_at = _now_iso()
        identity = identity or {}
        with self._connect() as connection:
            for record in records:
                message_id = str(record.get("message_id", ""))
                enriched_record = {
                    **record,
                    "client_id": record.get("client_id") or identity.get("client_id"),
                    "contract_id": record.get("contract_id") or identity.get("contract_id"),
                    "assignment_id": record.get("assignment_id") or identity.get("assignment_id"),
                }
                try:
                    connection.execute(
                        """
                        INSERT INTO telemetry_records (
                            message_id, client_id, device_id, kit_id, contract_id, assignment_id,
                            event_time, sequence_number, scenario, payload_json, inserted_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            message_id,
                            enriched_record.get("client_id"),
                            str(enriched_record.get("device_id", "unknown")),
                            enriched_record.get("kit_id"),
                            enriched_record.get("contract_id"),
                            enriched_record.get("assignment_id"),
                            str(enriched_record.get("event_time", inserted_at)),
                            enriched_record.get("sequence_number"),
                            enriched_record.get("scenario"),
                            json.dumps(enriched_record, ensure_ascii=False, sort_keys=True),
                            inserted_at,
                        ),
                    )
                    new_records.append(enriched_record)
                except sqlite3.IntegrityError:
                    duplicate_records.append(enriched_record)
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
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Une prediction technique est toujours rattachee au client/kit connu au moment du calcul.
        predicted_at = _now_iso()
        identity = identity or {}
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
            "client_id": identity.get("client_id") or latest.get("client_id"),
            "contract_id": identity.get("contract_id") or latest.get("contract_id"),
            "assignment_id": identity.get("assignment_id") or latest.get("assignment_id"),
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
                    prediction_id, client_id, device_id, kit_id, contract_id, assignment_id,
                    predicted_at, window_started_at, window_ended_at, records_used, maintenance_probability,
                    security_probability, risk_score, risk_level, alert_priority,
                    recommended_action, maintenance_prediction_json, security_prediction_json,
                    alert_json, feature_snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction_id,
                    prediction_payload["client_id"],
                    device_id,
                    kit_id,
                    prediction_payload["contract_id"],
                    prediction_payload["assignment_id"],
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
                    device_id, kit_id, client_id, contract_id, assignment_id,
                    last_event_time, last_prediction_at, status,
                    risk_level, risk_score, alert_priority, recommended_action,
                    latest_payload_json, latest_prediction_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    kit_id = excluded.kit_id,
                    client_id = excluded.client_id,
                    contract_id = excluded.contract_id,
                    assignment_id = excluded.assignment_id,
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
                    prediction_payload["client_id"],
                    prediction_payload["contract_id"],
                    prediction_payload["assignment_id"],
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

    def list_predictions(
        self,
        *,
        client_id: str | None = None,
        kit_id: str | None = None,
        device_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if client_id:
            clauses.append("client_id = ?")
            params.append(client_id)
        if kit_id:
            clauses.append("kit_id = ?")
            params.append(kit_id)
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM prediction_history
                {where}
                ORDER BY predicted_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._prediction_from_row(row) for row in rows]

    def save_customer_decision(self, *, input_snapshot: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        # Table d'audit: snapshot complet recu/prepare + resultat exact retourne par le moteur.
        created_at = _now_iso()
        identity = result.get("identity") or input_snapshot.get("identity") or {}
        customer = input_snapshot.get("customer") or {}
        scores = result.get("scores") or {}
        decision = result.get("decision") or {}
        payload = {
            "decision_id": result.get("decision_id") or f"customer-decision-{input_snapshot.get('request_id')}",
            "request_id": result.get("request_id") or input_snapshot.get("request_id"),
            "client_id": identity.get("client_id"),
            "kit_id": identity.get("kit_id"),
            "device_id": identity.get("device_id"),
            "contract_id": identity.get("contract_id"),
            "assignment_id": identity.get("assignment_id"),
            "as_of": result.get("as_of") or input_snapshot.get("as_of"),
            "identity_status": result.get("identity_status", "unknown"),
            "client_value_score": scores.get("client_value"),
            "payment_risk_score": scores.get("payment_risk"),
            "operational_risk_score": scores.get("operational_risk"),
            "intervention_priority_score": scores.get("intervention_priority"),
            "recommended_action": decision.get("recommended_action"),
            "priority": decision.get("priority"),
            "confidence": result.get("confidence"),
            "input_snapshot": input_snapshot,
            "result": result,
            "created_at": created_at,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customer_decision_history (
                    decision_id, request_id, client_id, kit_id, device_id, contract_id,
                    assignment_id, as_of, identity_status, client_value_score,
                    payment_risk_score, operational_risk_score, intervention_priority_score,
                    recommended_action, priority, confidence, input_snapshot_json,
                    result_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    request_id = excluded.request_id,
                    client_id = excluded.client_id,
                    kit_id = excluded.kit_id,
                    device_id = excluded.device_id,
                    contract_id = excluded.contract_id,
                    assignment_id = excluded.assignment_id,
                    as_of = excluded.as_of,
                    identity_status = excluded.identity_status,
                    client_value_score = excluded.client_value_score,
                    payment_risk_score = excluded.payment_risk_score,
                    operational_risk_score = excluded.operational_risk_score,
                    intervention_priority_score = excluded.intervention_priority_score,
                    recommended_action = excluded.recommended_action,
                    priority = excluded.priority,
                    confidence = excluded.confidence,
                    input_snapshot_json = excluded.input_snapshot_json,
                    result_json = excluded.result_json,
                    created_at = excluded.created_at
                """,
                (
                    payload["decision_id"],
                    payload["request_id"],
                    payload["client_id"],
                    payload["kit_id"],
                    payload["device_id"],
                    payload["contract_id"],
                    payload["assignment_id"],
                    payload["as_of"],
                    payload["identity_status"],
                    payload["client_value_score"],
                    payload["payment_risk_score"],
                    payload["operational_risk_score"],
                    payload["intervention_priority_score"],
                    payload["recommended_action"],
                    payload["priority"],
                    payload["confidence"],
                    json.dumps(input_snapshot, ensure_ascii=False, sort_keys=True),
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
        if payload["client_id"]:
            # Met a jour la fiche client rapide consommee par le frontend.
            self.upsert_customer(
                identity=identity,
                customer=customer,
                latest_scores=scores,
                latest_decision_id=payload["decision_id"],
                latest_decision_at=created_at,
            )
        return payload

    def upsert_customer(
        self,
        *,
        identity: dict[str, Any],
        customer: dict[str, Any] | None = None,
        latest_scores: dict[str, Any] | None = None,
        latest_decision_id: str | None = None,
        latest_decision_at: str | None = None,
    ) -> dict[str, Any] | None:
        # Fiche client locale: derniere vision connue, pas source de verite metier.
        client_id = identity.get("client_id")
        if not client_id:
            return None
        customer = customer or {}
        latest_scores = latest_scores or {}
        updated_at = _now_iso()
        payload = {
            "client_id": client_id,
            "latest_kit_id": identity.get("kit_id"),
            "latest_device_id": identity.get("device_id"),
            "latest_contract_id": identity.get("contract_id"),
            "latest_assignment_id": identity.get("assignment_id"),
            "customer_segment": customer.get("customer_segment"),
            "tenure_months": customer.get("tenure_months"),
            "active_contracts": customer.get("active_contracts"),
            "latest_client_value_score": latest_scores.get("client_value"),
            "latest_payment_risk_score": latest_scores.get("payment_risk"),
            "latest_operational_risk_score": latest_scores.get("operational_risk"),
            "latest_intervention_priority_score": latest_scores.get("intervention_priority"),
            "latest_decision_id": latest_decision_id,
            "latest_decision_at": latest_decision_at,
            "raw_customer": customer,
            "raw_identity": identity,
            "updated_at": updated_at,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customers (
                    client_id, latest_kit_id, latest_device_id, latest_contract_id,
                    latest_assignment_id, customer_segment, tenure_months, active_contracts,
                    latest_client_value_score, latest_payment_risk_score,
                    latest_operational_risk_score, latest_intervention_priority_score,
                    latest_decision_id, latest_decision_at, raw_customer_json,
                    raw_identity_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    latest_kit_id = COALESCE(excluded.latest_kit_id, customers.latest_kit_id),
                    latest_device_id = COALESCE(excluded.latest_device_id, customers.latest_device_id),
                    latest_contract_id = COALESCE(excluded.latest_contract_id, customers.latest_contract_id),
                    latest_assignment_id = COALESCE(excluded.latest_assignment_id, customers.latest_assignment_id),
                    customer_segment = COALESCE(excluded.customer_segment, customers.customer_segment),
                    tenure_months = COALESCE(excluded.tenure_months, customers.tenure_months),
                    active_contracts = COALESCE(excluded.active_contracts, customers.active_contracts),
                    latest_client_value_score = COALESCE(excluded.latest_client_value_score, customers.latest_client_value_score),
                    latest_payment_risk_score = COALESCE(excluded.latest_payment_risk_score, customers.latest_payment_risk_score),
                    latest_operational_risk_score = COALESCE(excluded.latest_operational_risk_score, customers.latest_operational_risk_score),
                    latest_intervention_priority_score = COALESCE(excluded.latest_intervention_priority_score, customers.latest_intervention_priority_score),
                    latest_decision_id = COALESCE(excluded.latest_decision_id, customers.latest_decision_id),
                    latest_decision_at = COALESCE(excluded.latest_decision_at, customers.latest_decision_at),
                    raw_customer_json = excluded.raw_customer_json,
                    raw_identity_json = excluded.raw_identity_json,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["client_id"],
                    payload["latest_kit_id"],
                    payload["latest_device_id"],
                    payload["latest_contract_id"],
                    payload["latest_assignment_id"],
                    payload["customer_segment"],
                    payload["tenure_months"],
                    payload["active_contracts"],
                    payload["latest_client_value_score"],
                    payload["latest_payment_risk_score"],
                    payload["latest_operational_risk_score"],
                    payload["latest_intervention_priority_score"],
                    payload["latest_decision_id"],
                    payload["latest_decision_at"],
                    json.dumps(customer, ensure_ascii=False, sort_keys=True),
                    json.dumps(identity, ensure_ascii=False, sort_keys=True),
                    updated_at,
                ),
            )
        return payload

    def list_customers(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM customers
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._customer_from_row(row) for row in rows]

    def get_customer(self, client_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM customers WHERE client_id = ?", (client_id,)).fetchone()
        return self._customer_from_row(row) if row else None

    def list_customer_decisions(
        self,
        *,
        client_id: str | None = None,
        kit_id: str | None = None,
        device_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if client_id:
            clauses.append("client_id = ?")
            params.append(client_id)
        if kit_id:
            clauses.append("kit_id = ?")
            params.append(kit_id)
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM customer_decision_history
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._customer_decision_from_row(row) for row in rows]

    def get_customer_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM customer_decision_history WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        return self._customer_decision_from_row(row) if row else None

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

    def _customer_decision_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        decision = dict(row)
        decision["input_snapshot"] = json.loads(decision.pop("input_snapshot_json"))
        decision["result"] = json.loads(decision.pop("result_json"))
        return decision

    def _customer_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        customer = dict(row)
        customer["raw_customer"] = json.loads(customer.pop("raw_customer_json"))
        customer["raw_identity"] = json.loads(customer.pop("raw_identity_json"))
        return customer
