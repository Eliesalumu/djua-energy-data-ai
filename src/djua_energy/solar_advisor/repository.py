from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


DEFAULT_DATABASE_PATH = Path("data/runtime/solar_advisor.sqlite")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SolarAdvisorRepository:
    def __init__(self, database_path: str | Path | None = None) -> None:
        env_path = os.getenv("DJUA_SOLAR_ADVISOR_DB")
        self.database_path = Path(database_path or env_path or DEFAULT_DATABASE_PATH)
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
                CREATE TABLE IF NOT EXISTS advisor_recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    source TEXT NOT NULL,
                    city TEXT,
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    consumption_json TEXT NOT NULL,
                    sizing_json TEXT NOT NULL,
                    recommendation_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_advisor_customer_created
                    ON advisor_recommendations(customer_id, created_at);

                CREATE TABLE IF NOT EXISTS advisor_contact_requests (
                    contact_request_id TEXT PRIMARY KEY,
                    recommendation_id TEXT NOT NULL,
                    customer_name TEXT,
                    phone TEXT,
                    email TEXT,
                    message TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(recommendation_id) REFERENCES advisor_recommendations(recommendation_id)
                );
                """
            )

    def save_recommendation(self, payload: dict[str, Any]) -> None:
        request = payload["request"]
        now = _now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO advisor_recommendations (
                    recommendation_id, customer_id, source, city, created_at,
                    request_json, consumption_json, sizing_json, recommendation_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["recommendation_id"],
                    request.get("customer_id"),
                    request.get("source", "manual"),
                    request.get("city") or request.get("region"),
                    now,
                    json.dumps(request, ensure_ascii=False, sort_keys=True),
                    json.dumps(payload["consumption"], ensure_ascii=False, sort_keys=True),
                    json.dumps(payload["sizing"], ensure_ascii=False, sort_keys=True),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def get_recommendation(self, recommendation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT recommendation_json FROM advisor_recommendations WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
        return json.loads(row["recommendation_json"]) if row else None

    def list_recommendations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT recommendation_json
                FROM advisor_recommendations
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(row["recommendation_json"]) for row in rows]

    def save_contact_request(self, recommendation_id: str, contact: dict[str, Any]) -> dict[str, Any]:
        created_at = _now_iso()
        payload = {
            "contact_request_id": f"contact-{recommendation_id}-{created_at}",
            "recommendation_id": recommendation_id,
            "customer_name": contact.get("name"),
            "phone": contact.get("phone"),
            "email": contact.get("email"),
            "message": contact.get("message", "Demande de rappel Orange Energy."),
            "status": "pending",
            "created_at": created_at,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO advisor_contact_requests (
                    contact_request_id, recommendation_id, customer_name,
                    phone, email, message, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["contact_request_id"],
                    recommendation_id,
                    payload["customer_name"],
                    payload["phone"],
                    payload["email"],
                    payload["message"],
                    payload["status"],
                    payload["created_at"],
                ),
            )
        return payload
