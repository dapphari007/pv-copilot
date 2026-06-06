"""Local persistence for analyzed cases and uploaded documents (SQLite).

Stores, for every analysis run: the input prompt/narrative, the source (manual
or uploaded file), the stored file path, and the extracted entities / analysis /
report as JSON. Uploaded files are copied into ``uploads/`` and only their path
is recorded in the database (the blob stays on disk).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import config
from src.logging_config import get_logger

log = get_logger("storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    case_id         TEXT,
    source          TEXT,            -- 'manual' | 'upload'
    file_path       TEXT,            -- relative path under uploads/ (nullable)
    file_name       TEXT,
    prompt          TEXT NOT NULL,   -- the narrative / prompt analyzed
    drug            TEXT,
    seriousness     TEXT,
    causality       TEXT,
    vector_backend  TEXT,
    embedding_model TEXT,
    rag_engine      TEXT,
    entities_json   TEXT,
    analysis_json   TEXT,
    report_json     TEXT
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_DB_READY = False


def init_db() -> None:
    """Create the schema once per process (cheap no-op afterwards)."""
    global _DB_READY
    if _DB_READY:
        return
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    _DB_READY = True
    log.info("SQLite ready at %s", config.SQLITE_PATH)


def save_upload(file_bytes: bytes, file_name: str) -> str:
    """Persist an uploaded file under ``uploads/`` and return its relative path."""
    safe = Path(file_name).name or "upload.bin"
    stored = f"{uuid.uuid4().hex[:8]}_{safe}"
    dest = config.UPLOAD_DIR / stored
    dest.write_bytes(file_bytes)
    log.info("Stored upload %s (%d bytes)", dest.name, len(file_bytes))
    return str(dest.relative_to(config.PROJECT_ROOT))


def save_case(
    *,
    prompt: str,
    entities: dict[str, Any],
    analysis: dict[str, Any],
    report: dict[str, Any],
    source: str = "manual",
    file_path: str | None = None,
    file_name: str | None = None,
    settings: dict[str, Any] | None = None,
) -> str:
    """Persist a completed analysis run; returns the new row id."""
    init_db()
    row_id = uuid.uuid4().hex
    settings = settings or {}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO cases (
                id, created_at, case_id, source, file_path, file_name, prompt,
                drug, seriousness, causality, vector_backend, embedding_model,
                rag_engine, entities_json, analysis_json, report_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row_id,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                report.get("case_information", {}).get("Case ID", ""),
                source, file_path, file_name, prompt,
                entities.get("drug", ""),
                analysis.get("seriousness", ""),
                analysis.get("causality", ""),
                settings.get("vector_backend", ""),
                settings.get("embedding_model", ""),
                settings.get("rag_engine", ""),
                json.dumps(entities, ensure_ascii=False),
                json.dumps(analysis, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
            ),
        )
    log.info("Saved case %s (drug=%s, serious=%s)", row_id[:8],
             entities.get("drug", "?"), analysis.get("seriousness", "?"))
    return row_id


def list_cases(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent case summaries (no large JSON blobs)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, created_at, case_id, source, file_name, prompt, drug,
                      seriousness, causality, embedding_model, vector_backend, rag_engine
               FROM cases ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_case(row_id: str) -> dict[str, Any] | None:
    """Return a full case record with parsed JSON fields."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return None
    record = dict(row)
    for field in ("entities_json", "analysis_json", "report_json"):
        record[field.replace("_json", "")] = json.loads(record.pop(field) or "{}")
    return record


def count_cases() -> int:
    init_db()
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
