"""
Healthcare Orchestra — Database Adapter (synchronous SQLite).

Provides a simple synchronous Database class that the agents use to:
- Sync data from HealthBridge FHIR API
- Read/write patient, medication, lab, follow-up, appointment records
- Log agent actions, communications, and audit events

Uses SQLite for local persistence. Falls back gracefully when HealthBridge
is unavailable.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

from config import config

logger = logging.getLogger("healthcare_orchestra.db_adapter")

# ---------------------------------------------------------------------------
# Schema DDL (created automatically on first use)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    id                  TEXT PRIMARY KEY,
    healthbridge_id     TEXT UNIQUE,
    first_name          TEXT,
    last_name           TEXT,
    phone               TEXT,
    email               TEXT,
    address             TEXT,
    date_of_birth       TEXT,
    gender              TEXT,
    is_active           INTEGER DEFAULT 1,
    risk_score          TEXT DEFAULT 'LOW',
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS medications (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    name                TEXT,
    dosage              TEXT,
    frequency           TEXT,
    route               TEXT,
    prescribed_date     TEXT,
    end_date            TEXT,
    refill_count        INTEGER DEFAULT 0,
    refill_threshold    INTEGER DEFAULT 3,
    is_active           INTEGER DEFAULT 1,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS adherence_log (
    id                  TEXT PRIMARY KEY,
    medication_id       TEXT NOT NULL,
    patient_id          TEXT NOT NULL,
    scheduled_date      TEXT NOT NULL,
    taken               INTEGER DEFAULT 0,
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (medication_id) REFERENCES medications(id),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS lab_orders (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    test_name           TEXT,
    test_code           TEXT,
    ordered_date        TEXT,
    result_value        TEXT,
    result_unit         TEXT,
    reference_range     TEXT,
    is_abnormal         INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'pending',
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    provider_name       TEXT,
    appointment_type    TEXT,
    scheduled_date      TEXT,
    scheduled_time      TEXT,
    status              TEXT DEFAULT 'scheduled',
    notified            INTEGER DEFAULT 0,
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    follow_up_type      TEXT,
    description         TEXT,
    due_date            TEXT,
    status              TEXT DEFAULT 'pending',
    days_overdue        INTEGER DEFAULT 0,
    escalated           INTEGER DEFAULT 0,
    escalation_level    TEXT DEFAULT 'none',
    created_at          TEXT DEFAULT (datetime('now')),
    completed_at        TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS agent_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name          TEXT NOT NULL,
    action              TEXT,
    patient_id          TEXT,
    details             TEXT,
    status              TEXT DEFAULT 'success',
    executed_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS communication_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    channel             TEXT NOT NULL,
    recipient           TEXT,
    subject             TEXT,
    body                TEXT,
    status              TEXT DEFAULT 'sent',
    sent_at             TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    action              TEXT NOT NULL,
    entity_type         TEXT,
    entity_id           TEXT,
    user_id             TEXT,
    details             TEXT,
    ip_address          TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pharmacy_interactions (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    medication_id       TEXT,
    interaction_type    TEXT,
    details             TEXT,
    status              TEXT DEFAULT 'pending',
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS insurance_claims (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    claim_number        TEXT,
    payer_name          TEXT,
    amount              REAL,
    status              TEXT DEFAULT 'submitted',
    submitted_date      TEXT,
    stalled_reason      TEXT,
    flagged             INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS voice_call_eligibility (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    eligible            INTEGER DEFAULT 0,
    reason              TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS family_summaries (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    summary_type        TEXT DEFAULT 'weekly',
    summary_text        TEXT,
    generated_at        TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_medications_patient ON medications(patient_id);
CREATE INDEX IF NOT EXISTS idx_adherence_patient ON adherence_log(patient_id);
CREATE INDEX IF NOT EXISTS idx_adherence_med ON adherence_log(medication_id);
CREATE INDEX IF NOT EXISTS idx_followups_patient ON follow_ups(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_lab_orders_patient ON lab_orders(patient_id);
CREATE INDEX IF NOT EXISTS idx_claims_patient ON insurance_claims(patient_id);
CREATE INDEX IF NOT EXISTS idx_agent_log_agent ON agent_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_communication_log_channel ON communication_log(channel);
"""


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------


class Database:
    """Synchronous SQLite-backed database for agent operations.

    Provides all CRUD and query methods needed by the 10 healthcare agents.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or config.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        try:
            conn = self._get_conn()
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        except Exception as exc:
            logger.warning("Schema initialisation warning: %s", exc)

    # ------------------------------------------------------------------
    # HealthBridge sync
    # ------------------------------------------------------------------

    def sync_from_healthbridge(self) -> dict[str, int]:
        """Pull patient, medication, lab, and appointment data from HealthBridge FHIR API.

        Returns a dict with counts of synced records.
        """
        counts: dict[str, int] = {
            "patients": 0,
            "medications": 0,
            "lab_orders": 0,
            "appointments": 0,
        }
        api_url = config.HEALTHBRIDGE_API_URL

        # -- Sync patients --
        try:
            resp = requests.get(f"{api_url}/fhir/Patient", timeout=10)
            if resp.status_code == 200:
                bundle = resp.json()
                for entry in bundle.get("entry", []):
                    res = entry.get("resource", {})
                    patient_id = res.get("id", str(uuid.uuid4()))
                    name = res.get("name", [{}])[0]
                    given = " ".join(name.get("given", []))
                    family = name.get("family", "")
                    telecom = res.get("telecom", [])
                    phone = ""
                    email = ""
                    for t in telecom:
                        if t.get("system") == "phone":
                            phone = t.get("value", "")
                        elif t.get("system") == "email":
                            email = t.get("value", "")
                    address_list = res.get("address", [])
                    address = (
                        address_list[0].get("text", "") if address_list else ""
                    )
                    dob = res.get("birthDate", "")
                    gender = res.get("gender", "")

                    self._upsert_patient(
                        healthbridge_id=patient_id,
                        first_name=given,
                        last_name=family,
                        phone=phone,
                        email=email,
                        address=address,
                        date_of_birth=dob,
                        gender=gender,
                    )
                    counts["patients"] += 1
        except requests.RequestException:
            logger.warning("HealthBridge sync (patients) failed — skipping")
        except Exception as exc:
            logger.warning("Patient sync error: %s", exc)

        # -- Sync medications --
        try:
            resp = requests.get(f"{api_url}/fhir/MedicationRequest", timeout=10)
            if resp.status_code == 200:
                bundle = resp.json()
                for entry in bundle.get("entry", []):
                    res = entry.get("resource", {})
                    med_id = res.get("id", str(uuid.uuid4()))
                    subject = res.get("subject", {})
                    ref = subject.get("reference", "")
                    hb_patient_id = ref.replace("Patient/", "") if ref else ""

                    local_patient = self._find_patient_by_hb_id(hb_patient_id)
                    if not local_patient:
                        continue

                    med_name = (
                        res.get("medicationCodeableConcept", {})
                        .get("text", "Unknown")
                    )
                    dosage_info = res.get("dosageInstruction", [{}])[0]
                    dosage = dosage_info.get("text", "")
                    timing = dosage_info.get("timing", {})
                    code = timing.get("code", {}).get("text", "")
                    frequency = code or ""
                    route = (
                        dosage_info.get("route", {})
                        .get("text", "")
                    )

                    self._upsert_medication(
                        patient_id=local_patient["id"],
                        name=med_name,
                        dosage=dosage,
                        frequency=frequency,
                        route=route,
                    )
                    counts["medications"] += 1
        except requests.RequestException:
            logger.warning("HealthBridge sync (medications) failed — skipping")
        except Exception as exc:
            logger.warning("Medication sync error: %s", exc)

        # -- Sync lab orders --
        try:
            resp = requests.get(f"{api_url}/fhir/Observation", timeout=10)
            if resp.status_code == 200:
                bundle = resp.json()
                for entry in bundle.get("entry", []):
                    res = entry.get("resource", {})
                    obs_id = res.get("id", str(uuid.uuid4()))
                    subject = res.get("subject", {})
                    ref = subject.get("reference", "")
                    hb_patient_id = ref.replace("Patient/", "") if ref else ""

                    local_patient = self._find_patient_by_hb_id(hb_patient_id)
                    if not local_patient:
                        continue

                    code_info = res.get("code", {})
                    test_name = code_info.get("text", "Unknown")
                    test_code = code_info.get("coding", [{}])[0].get("code", "")
                    value_qty = res.get("valueQuantity", {})
                    result_value = str(value_qty.get("value", ""))
                    result_unit = value_qty.get("unit", "")
                    ref_range_list = res.get("referenceRange", [])
                    ref_range = (
                        ref_range_list[0].get("text", "") if ref_range_list else ""
                    )
                    interpretation = res.get("interpretation", [{}])[0]
                    is_abnormal = 1 if interpretation.get("text", "").lower() in (
                        "abnormal", "high", "low", "critical"
                    ) else 0

                    self._upsert_lab_order(
                        patient_id=local_patient["id"],
                        test_name=test_name,
                        test_code=test_code,
                        result_value=result_value,
                        result_unit=result_unit,
                        reference_range=ref_range,
                        is_abnormal=is_abnormal,
                    )
                    counts["lab_orders"] += 1
        except requests.RequestException:
            logger.warning("HealthBridge sync (lab orders) failed — skipping")
        except Exception as exc:
            logger.warning("Lab sync error: %s", exc)

        # -- Sync appointments --
        try:
            resp = requests.get(f"{api_url}/fhir/Appointment", timeout=10)
            if resp.status_code == 200:
                bundle = resp.json()
                for entry in bundle.get("entry", []):
                    res = entry.get("resource", {})
                    apt_id = res.get("id", str(uuid.uuid4()))
                    participants = res.get("participant", [])
                    hb_patient_id = ""
                    for p in participants:
                        actor = p.get("actor", {})
                        ref = actor.get("reference", "")
                        if ref.startswith("Patient/"):
                            hb_patient_id = ref.replace("Patient/", "")
                            break

                    local_patient = self._find_patient_by_hb_id(hb_patient_id)
                    if not local_patient:
                        continue

                    start = res.get("start", "")
                    appointment_type = (
                        res.get("appointmentType", {}).get("text", "General")
                    )
                    status = res.get("status", "scheduled")
                    desc = res.get("description", "")

                    if start:
                        try:
                            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                            date_str = dt.strftime("%Y-%m-%d")
                            time_str = dt.strftime("%H:%M:%S")
                        except ValueError:
                            date_str = start[:10]
                            time_str = start[11:19] if len(start) >= 19 else ""

                        self._upsert_appointment(
                            patient_id=local_patient["id"],
                            provider_name=desc,
                            appointment_type=appointment_type,
                            scheduled_date=date_str,
                            scheduled_time=time_str,
                            status=status,
                        )
                        counts["appointments"] += 1
        except requests.RequestException:
            logger.warning("HealthBridge sync (appointments) failed — skipping")
        except Exception as exc:
            logger.warning("Appointment sync error: %s", exc)

        logger.info(
            "HealthBridge sync complete: %d patients, %d medications, "
            "%d lab orders, %d appointments",
            counts["patients"],
            counts["medications"],
            counts["lab_orders"],
            counts["appointments"],
        )
        return counts

    def _upsert_patient(
        self,
        healthbridge_id: str,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        address: str = "",
        date_of_birth: str = "",
        gender: str = "",
    ) -> str:
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id FROM patients WHERE healthbridge_id = ?",
            (healthbridge_id,),
        ).fetchone()
        now = datetime.utcnow().isoformat()
        if existing:
            conn.execute(
                """UPDATE patients SET first_name=?, last_name=?, phone=?,
                   email=?, address=?, date_of_birth=?, gender=?,
                   updated_at=? WHERE healthbridge_id=?""",
                (first_name, last_name, phone, email, address,
                 date_of_birth, gender, now, healthbridge_id),
            )
            patient_id = existing["id"]
        else:
            patient_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO patients (id, healthbridge_id, first_name,
                   last_name, phone, email, address,
                   date_of_birth, gender, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (patient_id, healthbridge_id, first_name, last_name,
                 phone, email, address, date_of_birth, gender, now, now),
            )
        conn.commit()
        return patient_id

    def _find_patient_by_hb_id(self, hb_id: str) -> dict | None:
        if not hb_id:
            return None
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM patients WHERE healthbridge_id = ?",
            (hb_id,),
        ).fetchone()
        return dict(row) if row else None

    def _upsert_medication(
        self,
        patient_id: str,
        name: str,
        dosage: str = "",
        frequency: str = "",
        route: str = "",
    ) -> str:
        conn = self._get_conn()
        med_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO medications (id, patient_id, name, dosage,
               frequency, route, prescribed_date, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (med_id, patient_id, name, dosage, frequency,
             route, now[:10], now),
        )
        conn.commit()
        return med_id

    def _upsert_lab_order(
        self,
        patient_id: str,
        test_name: str,
        test_code: str = "",
        result_value: str = "",
        result_unit: str = "",
        reference_range: str = "",
        is_abnormal: int = 0,
    ) -> str:
        conn = self._get_conn()
        lab_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO lab_orders (id, patient_id, test_name, test_code,
               ordered_date, result_value, result_unit, reference_range,
               is_abnormal, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (lab_id, patient_id, test_name, test_code,
             now[:10], result_value, result_unit,
             reference_range, is_abnormal, "completed", now),
        )
        conn.commit()
        return lab_id

    def _upsert_appointment(
        self,
        patient_id: str,
        provider_name: str = "",
        appointment_type: str = "",
        scheduled_date: str = "",
        scheduled_time: str = "",
        status: str = "scheduled",
    ) -> str:
        conn = self._get_conn()
        apt_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO appointments (id, patient_id, provider_name,
               appointment_type, scheduled_date, scheduled_time,
               status, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (apt_id, patient_id, provider_name, appointment_type,
             scheduled_date, scheduled_time, status, now),
        )
        conn.commit()
        return apt_id

    # ------------------------------------------------------------------
    # Patient queries
    # ------------------------------------------------------------------

    def get_patients(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM patients WHERE is_active = 1 ORDER BY last_name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_patient(self, patient_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_patients_with_incomplete_data(self) -> list[dict]:
        """Return patients missing phone or address."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM patients WHERE is_active = 1
               AND (phone IS NULL OR phone = '' OR address IS NULL OR address = '')"""
        ).fetchall()
        return [dict(r) for r in rows]

    def create_patient(
        self,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        address: str = "",
        date_of_birth: str = "",
        gender: str = "",
    ) -> str:
        conn = self._get_conn()
        patient_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, phone, email,
               address, date_of_birth, gender, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (patient_id, first_name, last_name, phone, email,
             address, date_of_birth, gender, now, now),
        )
        conn.commit()
        return patient_id

    def update_patient(self, patient_id: str, **kwargs) -> bool:
        if not kwargs:
            return False
        sets = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [patient_id]
        conn = self._get_conn()
        conn.execute(
            f"UPDATE patients SET {sets}, updated_at=? WHERE id=?",
            values + [datetime.utcnow().isoformat()],
        )
        conn.commit()
        return conn.total_changes > 0

    # ------------------------------------------------------------------
    # Medication queries
    # ------------------------------------------------------------------

    def get_medications(self, patient_id: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if patient_id:
            rows = conn.execute(
                "SELECT * FROM medications WHERE patient_id = ? AND is_active = 1",
                (patient_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM medications WHERE is_active = 1"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_medications_approaching_refill(self) -> list[dict]:
        """Return medications where refill_count <= refill_threshold."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT m.*, p.first_name, p.last_name, p.phone
               FROM medications m
               JOIN patients p ON p.id = m.patient_id
               WHERE m.is_active = 1
               AND m.refill_count <= m.refill_threshold"""
        ).fetchall()
        return [dict(r) for r in rows]

    def create_medication(
        self,
        patient_id: str,
        name: str,
        dosage: str = "",
        frequency: str = "",
        route: str = "",
    ) -> str:
        conn = self._get_conn()
        med_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO medications (id, patient_id, name, dosage,
               frequency, route, prescribed_date, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (med_id, patient_id, name, dosage, frequency,
             route, now[:10], now),
        )
        conn.commit()
        return med_id

    # ------------------------------------------------------------------
    # Adherence tracking
    # ------------------------------------------------------------------

    def get_adherence_log(
        self, patient_id: str, days_back: int = 30
    ) -> list[dict]:
        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        rows = conn.execute(
            """SELECT a.*, m.name as medication_name
               FROM adherence_log a
               JOIN medications m ON m.id = a.medication_id
               WHERE a.patient_id = ? AND a.scheduled_date >= ?
               ORDER BY a.scheduled_date DESC""",
            (patient_id, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_adherence(
        self,
        medication_id: str,
        patient_id: str,
        scheduled_date: str,
        taken: int = 0,
        notes: str = "",
    ) -> str:
        conn = self._get_conn()
        log_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO adherence_log (id, medication_id, patient_id,
               scheduled_date, taken, notes)
               VALUES (?,?,?,?,?,?)""",
            (log_id, medication_id, patient_id, scheduled_date, taken, notes),
        )
        conn.commit()
        return log_id

    def get_adherence_rate(self, patient_id: str, days_back: int = 30) -> float:
        """Return adherence rate as a float 0.0–1.0."""
        cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        conn = self._get_conn()
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN taken=1 THEN 1 ELSE 0 END) as taken_count
               FROM adherence_log
               WHERE patient_id = ? AND scheduled_date >= ?""",
            (patient_id, cutoff),
        ).fetchone()
        if row and row["total"] > 0:
            return row["taken_count"] / row["total"]
        return 1.0  # no data = assume good

    def get_missed_doses(self, patient_id: str, days_back: int = 7) -> list[dict]:
        """Return doses that were not taken in the last N days."""
        cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT a.*, m.name as medication_name
               FROM adherence_log a
               JOIN medications m ON m.id = a.medication_id
               WHERE a.patient_id = ? AND a.taken = 0
               AND a.scheduled_date >= ?
               ORDER BY a.scheduled_date DESC""",
            (patient_id, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Lab order queries
    # ------------------------------------------------------------------

    def get_lab_orders(
        self, patient_id: str | None = None, abnormal_only: bool = False
    ) -> list[dict]:
        conn = self._get_conn()
        if patient_id and abnormal_only:
            rows = conn.execute(
                "SELECT * FROM lab_orders WHERE patient_id = ? AND is_abnormal = 1",
                (patient_id,),
            ).fetchall()
        elif patient_id:
            rows = conn.execute(
                "SELECT * FROM lab_orders WHERE patient_id = ?",
                (patient_id,),
            ).fetchall()
        elif abnormal_only:
            rows = conn.execute(
                "SELECT * FROM lab_orders WHERE is_abnormal = 1"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM lab_orders").fetchall()
        return [dict(r) for r in rows]

    def create_lab_order(
        self,
        patient_id: str,
        test_name: str,
        test_code: str = "",
        result_value: str = "",
        result_unit: str = "",
        reference_range: str = "",
        is_abnormal: int = 0,
    ) -> str:
        conn = self._get_conn()
        lab_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO lab_orders (id, patient_id, test_name, test_code,
               ordered_date, result_value, result_unit, reference_range,
               is_abnormal, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (lab_id, patient_id, test_name, test_code,
             now[:10], result_value, result_unit,
             reference_range, is_abnormal, "completed", now),
        )
        conn.commit()
        return lab_id

    # ------------------------------------------------------------------
    # Follow-up queries
    # ------------------------------------------------------------------

    def get_follow_ups(
        self, status: str | None = None, overdue_only: bool = False
    ) -> list[dict]:
        conn = self._get_conn()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if overdue_only:
            rows = conn.execute(
                """SELECT f.*, p.first_name, p.last_name, p.phone
                   FROM follow_ups f
                   JOIN patients p ON p.id = f.patient_id
                   WHERE f.status = 'pending' AND f.due_date < ?
                   ORDER BY f.due_date ASC""",
                (today,),
            ).fetchall()
        elif status:
            rows = conn.execute(
                """SELECT f.*, p.first_name, p.last_name, p.phone
                   FROM follow_ups f
                   JOIN patients p ON p.id = f.patient_id
                   WHERE f.status = ?
                   ORDER BY f.due_date ASC""",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT f.*, p.first_name, p.last_name, p.phone
                   FROM follow_ups f
                   JOIN patients p ON p.id = f.patient_id
                   ORDER BY f.due_date ASC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def create_follow_up(
        self,
        patient_id: str,
        follow_up_type: str,
        description: str = "",
        due_date: str = "",
    ) -> str:
        conn = self._get_conn()
        fup_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        due = due_date or (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO follow_ups (id, patient_id, follow_up_type,
               description, due_date, created_at)
               VALUES (?,?,?,?,?,?)""",
            (fup_id, patient_id, follow_up_type, description, due, now),
        )
        conn.commit()
        return fup_id

    def complete_follow_up(self, follow_up_id: str) -> bool:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE follow_ups SET status='completed', completed_at=? WHERE id=?",
            (now, follow_up_id),
        )
        conn.commit()
        return conn.total_changes > 0

    # ------------------------------------------------------------------
    # Appointment queries
    # ------------------------------------------------------------------

    def get_appointments(
        self, patient_id: str | None = None, date: str | None = None
    ) -> list[dict]:
        conn = self._get_conn()
        if patient_id and date:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE patient_id = ? AND scheduled_date = ?",
                (patient_id, date),
            ).fetchall()
        elif patient_id:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE patient_id = ? ORDER BY scheduled_date",
                (patient_id,),
            ).fetchall()
        elif date:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE scheduled_date = ? ORDER BY scheduled_time",
                (date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM appointments ORDER BY scheduled_date"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_appointments_today_tomorrow(self) -> list[dict]:
        """Get appointments scheduled for today or tomorrow."""
        conn = self._get_conn()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT a.*, p.first_name, p.last_name, p.phone
               FROM appointments a
               JOIN patients p ON p.id = a.patient_id
               WHERE a.scheduled_date IN (?, ?)
               AND a.status IN ('scheduled', 'confirmed')
               ORDER BY a.scheduled_date, a.scheduled_time""",
            (today, tomorrow),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_appointment_notified(self, appointment_id: str) -> bool:
        conn = self._get_conn()
        conn.execute(
            "UPDATE appointments SET notified = 1 WHERE id = ?",
            (appointment_id,),
        )
        conn.commit()
        return conn.total_changes > 0

    # ------------------------------------------------------------------
    # Pharmacy interactions
    # ------------------------------------------------------------------

    def create_pharmacy_interaction(
        self,
        patient_id: str,
        medication_id: str = "",
        interaction_type: str = "",
        details: str = "",
    ) -> str:
        conn = self._get_conn()
        pi_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO pharmacy_interactions (id, patient_id, medication_id,
               interaction_type, details, created_at)
               VALUES (?,?,?,?,?,?)""",
            (pi_id, patient_id, medication_id, interaction_type, details, now),
        )
        conn.commit()
        return pi_id

    def get_pharmacy_interactions(
        self, patient_id: str | None = None, status: str | None = None
    ) -> list[dict]:
        conn = self._get_conn()
        if patient_id and status:
            rows = conn.execute(
                "SELECT * FROM pharmacy_interactions WHERE patient_id = ? AND status = ?",
                (patient_id, status),
            ).fetchall()
        elif patient_id:
            rows = conn.execute(
                "SELECT * FROM pharmacy_interactions WHERE patient_id = ?",
                (patient_id,),
            ).fetchall()
        elif status:
            rows = conn.execute(
                "SELECT * FROM pharmacy_interactions WHERE status = ?",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pharmacy_interactions").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Insurance claims
    # ------------------------------------------------------------------

    def get_insurance_claims(
        self,
        patient_id: str | None = None,
        stalled_only: bool = False,
    ) -> list[dict]:
        conn = self._get_conn()
        if patient_id and stalled_only:
            rows = conn.execute(
                """SELECT ic.*, p.first_name, p.last_name
                   FROM insurance_claims ic
                   JOIN patients p ON p.id = ic.patient_id
                   WHERE ic.patient_id = ? AND ic.flagged = 0
                   AND ic.status NOT IN ('paid', 'denied', 'closed')
                   ORDER BY ic.created_at DESC""",
                (patient_id,),
            ).fetchall()
        elif stalled_only:
            rows = conn.execute(
                """SELECT ic.*, p.first_name, p.last_name
                   FROM insurance_claims ic
                   JOIN patients p ON p.id = ic.patient_id
                   WHERE ic.flagged = 0
                   AND ic.status NOT IN ('paid', 'denied', 'closed')
                   ORDER BY ic.created_at DESC"""
            ).fetchall()
        elif patient_id:
            rows = conn.execute(
                "SELECT * FROM insurance_claims WHERE patient_id = ?",
                (patient_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM insurance_claims ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def flag_insurance_claim(self, claim_id: str) -> bool:
        conn = self._get_conn()
        conn.execute(
            "UPDATE insurance_claims SET flagged = 1 WHERE id = ?",
            (claim_id,),
        )
        conn.commit()
        return conn.total_changes > 0

    def create_insurance_claim(
        self,
        patient_id: str,
        claim_number: str = "",
        payer_name: str = "",
        amount: float = 0.0,
        status: str = "submitted",
    ) -> str:
        conn = self._get_conn()
        claim_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO insurance_claims (id, patient_id, claim_number,
               payer_name, amount, status, submitted_date, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (claim_id, patient_id, claim_number, payer_name,
             amount, status, now[:10], now),
        )
        conn.commit()
        return claim_id

    # ------------------------------------------------------------------
    # Voice call eligibility
    # ------------------------------------------------------------------

    def set_voice_call_eligibility(
        self, patient_id: str, eligible: bool, reason: str = ""
    ) -> str:
        conn = self._get_conn()
        vc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO voice_call_eligibility (id, patient_id, eligible,
               reason, created_at)
               VALUES (?,?,?,?,?)""",
            (vc_id, patient_id, 1 if eligible else 0, reason, now),
        )
        conn.commit()
        return vc_id

    def get_voice_eligible_patients(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT v.*, p.first_name, p.last_name, p.phone
               FROM voice_call_eligibility v
               JOIN patients p ON p.id = v.patient_id
               WHERE v.eligible = 1
               ORDER BY v.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Family summaries
    # ------------------------------------------------------------------

    def create_family_summary(
        self, patient_id: str, summary_text: str, summary_type: str = "weekly"
    ) -> str:
        conn = self._get_conn()
        fs_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO family_summaries (id, patient_id, summary_type,
               summary_text, generated_at)
               VALUES (?,?,?,?,?)""",
            (fs_id, patient_id, summary_type, summary_text, now),
        )
        conn.commit()
        return fs_id

    def get_family_summaries(
        self, patient_id: str, limit: int = 5
    ) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM family_summaries WHERE patient_id = ? ORDER BY generated_at DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_agent_action(
        self,
        agent_name: str,
        action: str,
        patient_id: str | None = None,
        details: str = "",
        status: str = "success",
    ) -> int:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        cur = conn.execute(
            """INSERT INTO agent_log (agent_name, action, patient_id,
               details, status, executed_at)
               VALUES (?,?,?,?,?,?)""",
            (agent_name, action, patient_id, details, status, now),
        )
        conn.commit()
        return cur.lastrowid or 0

    def log_communication(
        self,
        channel: str,
        recipient: str,
        subject: str = "",
        body: str = "",
        status: str = "sent",
    ) -> int:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        cur = conn.execute(
            """INSERT INTO communication_log (channel, recipient, subject,
               body, status, sent_at)
               VALUES (?,?,?,?,?,?)""",
            (channel, recipient, subject, body, status, now),
        )
        conn.commit()
        return cur.lastrowid or 0

    def log_audit(
        self,
        action: str,
        entity_type: str = "",
        entity_id: str = "",
        user_id: str = "",
        details: str = "",
        ip_address: str = "",
    ) -> int:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        cur = conn.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id,
               user_id, details, ip_address, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (action, entity_type, entity_id, user_id,
             details, ip_address, now),
        )
        conn.commit()
        return cur.lastrowid or 0

    # ------------------------------------------------------------------
    # Analytics helpers
    # ------------------------------------------------------------------

    def get_recent_agent_logs(
        self, agent_name: str | None = None, limit: int = 50
    ) -> list[dict]:
        conn = self._get_conn()
        if agent_name:
            rows = conn.execute(
                "SELECT * FROM agent_log WHERE agent_name = ? ORDER BY executed_at DESC LIMIT ?",
                (agent_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_log ORDER BY executed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_communications(
        self, channel: str | None = None, limit: int = 50
    ) -> list[dict]:
        conn = self._get_conn()
        if channel:
            rows = conn.execute(
                "SELECT * FROM communication_log WHERE channel = ? ORDER BY sent_at DESC LIMIT ?",
                (channel, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM communication_log ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Seed data (for development / demo)
    # ------------------------------------------------------------------

    def seed_sample_data(self) -> dict[str, int]:
        """Insert sample patients, medications, follow-ups, etc. for demo."""
        counts: dict[str, int] = {
            "patients": 0,
            "medications": 0,
            "follow_ups": 0,
            "appointments": 0,
            "lab_orders": 0,
        }

        sample_patients = [
            ("Alice", "Johnson", "+15551234567", "alice@example.com",
             "123 Main St, Springfield, IL", "1985-03-15", "female"),
            ("Bob", "Smith", "+15559876543", "bob@example.com",
             "456 Oak Ave, Portland, OR", "1972-07-22", "male"),
            ("Carol", "Williams", "", "carol@example.com",
             "", "1990-11-02", "female"),
            ("David", "Brown", "+15551112222", "david@example.com",
             "789 Pine Rd, Austin, TX", "1965-01-10", "male"),
            ("Eve", "Davis", "+15553334444", "",
             "321 Elm St, Denver, CO", "1978-09-05", "female"),
        ]

        patient_ids = []
        for first, last, phone, email, addr, dob, gender in sample_patients:
            pid = self.create_patient(
                first_name=first,
                last_name=last,
                phone=phone,
                email=email,
                address=addr,
                date_of_birth=dob,
                gender=gender,
            )
            patient_ids.append(pid)
            counts["patients"] += 1

        # Medications
        sample_meds = [
            (patient_ids[0], "Metformin", "500 mg", "Twice daily", "Oral"),
            (patient_ids[0], "Lisinopril", "10 mg", "Once daily", "Oral"),
            (patient_ids[1], "Atorvastatin", "20 mg", "Once daily", "Oral"),
            (patient_ids[1], "Aspirin", "81 mg", "Once daily", "Oral"),
            (patient_ids[2], "Levothyroxine", "50 mcg", "Once daily", "Oral"),
            (patient_ids[3], "Metoprolol", "25 mg", "Twice daily", "Oral"),
            (patient_ids[4], "Omeprazole", "20 mg", "Once daily", "Oral"),
        ]
        med_ids = []
        for pid, name, dosage, freq, route in sample_meds:
            mid = self.create_medication(pid, name, dosage, freq, route)
            med_ids.append(mid)
            counts["medications"] += 1

        # Adherence log entries (simulate some missed doses)
        today = datetime.utcnow()
        for mid in med_ids:
            for day_offset in range(7):
                day = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                taken = 0 if day_offset in (1, 4) else 1  # miss some days
                patient_id_for_med = self._get_conn().execute(
                    "SELECT patient_id FROM medications WHERE id = ?", (mid,)
                ).fetchone()
                if patient_id_for_med:
                    self.log_adherence(
                        medication_id=mid,
                        patient_id=patient_id_for_med["patient_id"],
                        scheduled_date=day,
                        taken=taken,
                    )

        # Follow-ups
        follow_ups = [
            (patient_ids[0], "checkup", "Annual physical checkup",
             (today + timedelta(days=1)).strftime("%Y-%m-%d")),
            (patient_ids[1], "lab", "Follow-up blood work",
             (today - timedelta(days=5)).strftime("%Y-%m-%d")),
            (patient_ids[2], "medication_review", "Medication review",
             (today - timedelta(days=2)).strftime("%Y-%m-%d")),
            (patient_ids[3], "specialist", "Cardiology follow-up",
             (today - timedelta(days=10)).strftime("%Y-%m-%d")),
        ]
        for pid, ftype, desc, due in follow_ups:
            self.create_follow_up(pid, ftype, desc, due)
            counts["follow_ups"] += 1

        # Appointments
        appointments = [
            (patient_ids[0], "Dr. Anderson", "General",
             today.strftime("%Y-%m-%d"), "10:30:00"),
            (patient_ids[1], "Dr. Barnes", "Lab",
             today.strftime("%Y-%m-%d"), "14:00:00"),
            (patient_ids[2], "Dr. Chen", "Follow-up",
             (today + timedelta(days=1)).strftime("%Y-%m-%d"), "09:00:00"),
            (patient_ids[3], "Dr. Davis", "Cardiology",
             (today + timedelta(days=1)).strftime("%Y-%m-%d"), "11:00:00"),
        ]
        for pid, provider, atype, sched_date, sched_time in appointments:
            self._upsert_appointment(
                patient_id=pid,
                provider_name=provider,
                appointment_type=atype,
                scheduled_date=sched_date,
                scheduled_time=sched_time,
            )
            counts["appointments"] += 1

        # Lab orders
        lab_data = [
            (patient_ids[0], "HbA1c", "4548-4", "7.2", "%", "< 5.7", 1),
            (patient_ids[0], "LDL Cholesterol", "18262-6", "130", "mg/dL",
             "< 100", 1),
            (patient_ids[1], "TSH", "3016-3", "2.5", "mIU/L", "0.4-4.0", 0),
            (patient_ids[2], "Vitamin D", "35365-6", "22", "ng/mL",
             "30-100", 1),
            (patient_ids[3], "Creatinine", "2160-0", "1.1", "mg/dL",
             "0.6-1.2", 0),
            (patient_ids[4], "Hemoglobin", "718-7", "13.5", "g/dL",
             "12.0-15.5", 0),
        ]
        for pid, tname, tcode, rval, runit, rrange, abnormal in lab_data:
            self.create_lab_order(
                patient_id=pid,
                test_name=tname,
                test_code=tcode,
                result_value=rval,
                result_unit=runit,
                reference_range=rrange,
                is_abnormal=abnormal,
            )
            counts["lab_orders"] += 1

        logger.info(
            "Sample data seeded: %d patients, %d medications, "
            "%d follow-ups, %d appointments, %d lab orders",
            counts["patients"], counts["medications"],
            counts["follow_ups"], counts["appointments"],
            counts["lab_orders"],
        )
        return counts
