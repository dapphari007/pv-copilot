"""SQLite persistence for the rebuilt multi-patient PV system.

A dedicated ``pv_cases`` table (separate from the legacy ``cases`` table) records
one row per detected patient case, tagged with an ``upload_id`` so the dashboard
can show CURRENT-upload statistics and the History page can show everything.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import config
from src.logging_config import get_logger

log = get_logger("storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pv_cases (
    id              TEXT PRIMARY KEY,
    upload_id       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    case_id         TEXT,
    patient_id      TEXT,
    file_name       TEXT,
    suspected_drug  TEXT,
    outcome         TEXT,
    seriousness     TEXT,
    causality       TEXT,
    case_json       TEXT,
    analysis_json   TEXT,
    report_json     TEXT,
    retrieved_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_pv_upload ON pv_cases(upload_id);
CREATE INDEX IF NOT EXISTS idx_pv_serious ON pv_cases(seriousness);
"""

_READY = False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    global _READY
    if _READY:
        return
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    _READY = True
    log.info("pv_cases table ready at %s", config.SQLITE_PATH)


def new_upload_id() -> str:
    return uuid.uuid4().hex[:12]


def save_case(upload_id: str, case: dict[str, Any], analysis: dict[str, Any],
              report: dict[str, Any], retrieved: list[dict[str, Any]],
              file_name: str | None = None) -> str:
    init_db()
    row_id = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            """INSERT INTO pv_cases (id, upload_id, created_at, case_id, patient_id,
               file_name, suspected_drug, outcome, seriousness, causality,
               case_json, analysis_json, report_json, retrieved_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row_id, upload_id,
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             report.get("case_information", {}).get("Case ID", ""),
             case.get("patient_id", ""), file_name,
             case.get("suspected_drug", ""), case.get("outcome", ""),
             analysis.get("seriousness", ""), analysis.get("causality", ""),
             json.dumps(case, ensure_ascii=False),
             json.dumps(analysis, ensure_ascii=False),
             json.dumps(report, ensure_ascii=False),
             json.dumps(retrieved, ensure_ascii=False)),
        )
    log.info("Saved pv_case %s (upload=%s, drug=%s, serious=%s)", row_id[:8],
             upload_id, case.get("suspected_drug", "?"), analysis.get("seriousness"))
    return row_id


def _row(record: dict[str, Any]) -> dict[str, Any]:
    for f in ("case_json", "analysis_json", "report_json", "retrieved_json"):
        record[f.replace("_json", "")] = json.loads(record.pop(f) or "null")
    return record


def list_cases(upload_id: str | None = None, seriousness: str | None = None,
               search: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    init_db()
    where, params = [], []
    if upload_id:
        where.append("upload_id = ?"); params.append(upload_id)
    if seriousness:
        where.append("seriousness = ?"); params.append(seriousness)
    if search:
        where.append("(case_id LIKE ? OR patient_id LIKE ? OR suspected_drug LIKE ?)")
        params += [f"%{search}%"] * 3
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT id, upload_id, created_at, case_id, patient_id, file_name,
                suspected_drug, outcome, seriousness, causality
                FROM pv_cases{clause} ORDER BY created_at DESC LIMIT ?""",
            (*params, limit)).fetchall()
    return [dict(r) for r in rows]


def get_case(row_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM pv_cases WHERE id = ?", (row_id,)).fetchone()
    return _row(dict(row)) if row else None


def upload_stats(upload_id: str) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT seriousness FROM pv_cases WHERE upload_id = ?", (upload_id,)
        ).fetchall()
    serious = sum(1 for r in rows if r["seriousness"] == "Serious")
    return {"cases_found": len(rows), "reports_generated": len(rows),
            "serious_cases": serious, "non_serious_cases": len(rows) - serious}
