from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROLES = {"customer", "technician", "support", "admin"}


def normalize_phone(phone: str) -> str:
    phone = re.sub(r"[ +().-]", "", phone)
    if not re.fullmatch(r"[0-9]{8,15}", phone):
        raise ValueError("Numero international attendu (8 a 15 chiffres).")
    return phone


class WhatsAppRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS whatsapp_users (
                    id INTEGER PRIMARY KEY, phone_number TEXT UNIQUE NOT NULL,
                    customer_id TEXT, role TEXT NOT NULL CHECK(role IN ('customer','technician','support','admin')),
                    display_name TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS whatsapp_device_access (
                    id INTEGER PRIMARY KEY, whatsapp_user_id INTEGER NOT NULL REFERENCES whatsapp_users(id),
                    kit_id TEXT, device_id TEXT NOT NULL, is_primary INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(whatsapp_user_id,device_id)
                );
                CREATE TABLE IF NOT EXISTS whatsapp_inbox (
                    message_id TEXT PRIMARY KEY, phone_number TEXT NOT NULL, body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', response TEXT, error_code TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_whatsapp_inbox_status ON whatsapp_inbox(status,created_at);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def upsert_user(self, phone: str, role: str, customer_id: str | None = None,
                    display_name: str = "", active: bool = True) -> dict:
        if role not in ROLES:
            raise ValueError("Role WhatsApp invalide.")
        phone = normalize_phone(phone)
        with self.connect() as db:
            db.execute("""INSERT INTO whatsapp_users(phone_number,role,customer_id,display_name,active)
                VALUES(?,?,?,?,?) ON CONFLICT(phone_number) DO UPDATE SET
                role=excluded.role, customer_id=excluded.customer_id,
                display_name=excluded.display_name, active=excluded.active""",
                (phone, role, customer_id, display_name, int(active)))
        return self.get_user(phone)

    def get_user(self, phone: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM whatsapp_users WHERE phone_number=?", (normalize_phone(phone),)).fetchone()
        return dict(row) if row else None

    def grant_device(self, phone: str, device_id: str, kit_id: str | None = None, primary: bool = False):
        user = self.get_user(phone)
        if not user or not device_id.strip():
            raise ValueError("Utilisateur ou device absent.")
        with self.connect() as db:
            if primary:
                db.execute("UPDATE whatsapp_device_access SET is_primary=0 WHERE whatsapp_user_id=?", (user["id"],))
            db.execute("""INSERT INTO whatsapp_device_access(whatsapp_user_id,device_id,kit_id,is_primary)
                VALUES(?,?,?,?) ON CONFLICT(whatsapp_user_id,device_id) DO UPDATE SET
                kit_id=excluded.kit_id,is_primary=excluded.is_primary""",
                (user["id"], device_id.strip(), kit_id, int(primary)))

    def revoke_device(self, phone: str, device_id: str):
        user = self.get_user(phone)
        if user:
            with self.connect() as db:
                db.execute("DELETE FROM whatsapp_device_access WHERE whatsapp_user_id=? AND device_id=?", (user["id"], device_id))

    def devices_for_user(self, user_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT device_id,kit_id,is_primary FROM whatsapp_device_access WHERE whatsapp_user_id=? ORDER BY device_id", (user_id,))]

    def registered_devices(self) -> list[dict]:
        """Devices registered through grants, including those awaiting telemetry."""
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT device_id, MAX(kit_id) AS kit_id FROM whatsapp_device_access GROUP BY device_id ORDER BY device_id")]

    def search_customers(self, term: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT DISTINCT customer_id,display_name FROM whatsapp_users WHERE role='customer' AND customer_id IS NOT NULL").fetchall()
        return [dict(row) for row in rows if term.casefold() in row["customer_id"].casefold()
                or term.casefold() in row["display_name"].casefold()][:20]

    def devices_for_customer(self, customer_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT DISTINCT a.device_id,a.kit_id
                FROM whatsapp_device_access a JOIN whatsapp_users u ON u.id=a.whatsapp_user_id
                WHERE u.customer_id=? AND u.role='customer'""", (customer_id,))]

    def enqueue(self, message_id: str, phone: str, body: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("INSERT OR IGNORE INTO whatsapp_inbox(message_id,phone_number,body) VALUES(?,?,?)",
                                (message_id, normalize_phone(phone), body))
            return cursor.rowcount == 1

    def claim_next(self) -> dict | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM whatsapp_inbox WHERE status='pending' ORDER BY created_at,message_id LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE whatsapp_inbox SET status='processing',updated_at=CURRENT_TIMESTAMP WHERE message_id=?", (row["message_id"],))
            return dict(row) if row else None

    def update_message(self, message_id: str, status: str, response: str | None = None, error_code: str | None = None):
        with self.connect() as db:
            db.execute("""UPDATE whatsapp_inbox SET status=?,response=COALESCE(?,response),error_code=?,
                updated_at=CURRENT_TIMESTAMP WHERE message_id=?""", (status, response, error_code, message_id))

    def message_status(self, message_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT message_id,status,error_code,updated_at FROM whatsapp_inbox WHERE message_id=?", (message_id,)).fetchone()
            return dict(row) if row else None
