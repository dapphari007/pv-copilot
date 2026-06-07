"""FastAPI backend for the Pharmacovigilance AI Copilot — API endpoints only.

All business logic lives in ``src/`` (see ``src/pipeline.py``). This module just
defines the HTTP surface: request/response models and thin handlers that
delegate. Run with:

    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import io
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config
from src import batch as batch_mod
from src import extraction, report as report_mod, storage, vectordb
from src.documents import read_document
from src.logging_config import get_logger
from src.pipeline import run_analysis
from src.settings_store import load_settings, save_settings

log = get_logger("api")

app = FastAPI(
    title="Pharmacovigilance AI Copilot API",
    version="1.0.0",
    description="Adverse-event entity extraction, RAG over FAERS, and AI case analysis.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    narrative: str = Field(..., min_length=1)
    case_id: str = "PV-2026-00001"
    report_date: str = ""


class SettingsRequest(BaseModel):
    vector_backend: str | None = None
    embedding_model: str | None = None
    rag_engine: str | None = None
    top_k: int | None = None


class GroqKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    return {
        "llm_available": config.llm_available(),
        "llm_model": config.GROQ_MODEL,
        "embedding_models": config.EMBEDDING_MODELS,
        "settings": load_settings(),
        "vector_backends": vectordb.backend_status(),
        "case_count": storage.count_cases(),
    }


@app.get("/settings")
def get_settings() -> dict[str, Any]:
    return load_settings()


@app.post("/settings")
def update_settings(req: SettingsRequest) -> dict[str, Any]:
    return save_settings(req.model_dump(exclude_none=True))


@app.post("/settings/groq-key")
def set_groq_key(req: GroqKeyRequest) -> dict[str, Any]:
    """Set the Groq API key at runtime (persisted to .env). Verifies it works."""
    config.set_groq_key(req.api_key)
    from src import llm
    llm._client_for.cache_clear()  # drop any cached client for the old key
    ok, detail = True, "Key set."
    try:
        llm.chat("test", "Reply with: OK", max_tokens=5)
    except Exception as exc:
        ok, detail = False, f"Key saved but a test call failed: {exc}"
    return {"llm_available": config.llm_available(), "verified": ok, "detail": detail}


# --------------------------------------------------------------------------- #
# Core pipeline
# --------------------------------------------------------------------------- #
@app.post("/extract")
def extract(req: AnalyzeRequest) -> dict[str, Any]:
    return extraction.extract_entities(req.narrative)


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    return run_analysis(
        req.narrative, case_id=req.case_id, report_date=req.report_date,
        source="manual", source_documents=["API request"],
    )


@app.post("/analyze/upload")
async def analyze_upload(
    file: UploadFile = File(...),
    case_id: str = "PV-2026-00001",
    report_date: str = "",
) -> dict[str, Any]:
    data = await file.read()
    text = read_document(data, file.filename or "upload")
    if not text.strip():
        raise HTTPException(422, "Could not extract text from the uploaded file.")
    stored_path = storage.save_upload(data, file.filename or "upload")
    return run_analysis(
        text, case_id=case_id, report_date=report_date, source="upload",
        file_path=stored_path, file_name=file.filename,
        source_documents=[file.filename or "uploaded document"],
    )


# --------------------------------------------------------------------------- #
# Batch analysis (multiple files and/or narratives)
# --------------------------------------------------------------------------- #
class BatchTextRequest(BaseModel):
    narratives: list[str] = Field(..., min_length=1)
    report_date: str = ""


class BatchExportRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1)


@app.post("/analyze/batch")
async def analyze_batch(
    files: list[UploadFile] = File(...),
    report_date: str = "",
) -> dict[str, Any]:
    """Analyze many uploaded files at once (proper concurrent batching)."""
    items = [
        batch_mod.BatchItem(file_name=f.filename, file_bytes=await f.read())
        for f in files
    ]
    results = batch_mod.run_batch(items, report_date=report_date)
    return {"count": len(results),
            "ok": sum(1 for r in results if r.get("ok")), "results": results}


@app.post("/analyze/batch-text")
def analyze_batch_text(req: BatchTextRequest) -> dict[str, Any]:
    """Analyze many free-text narratives at once."""
    items = [batch_mod.BatchItem(text=t) for t in req.narratives if t.strip()]
    if not items:
        raise HTTPException(422, "No non-empty narratives provided.")
    results = batch_mod.run_batch(items, report_date=req.report_date)
    return {"count": len(results),
            "ok": sum(1 for r in results if r.get("ok")), "results": results}


@app.post("/batch/export.{fmt}")
def batch_export(fmt: str, req: BatchExportRequest) -> StreamingResponse:
    """Combined download for a batch: zip of PDFs or a summary spreadsheet."""
    if fmt not in ("zip", "xlsx"):
        raise HTTPException(400, "Format must be zip or xlsx.")
    payload = batch_mod.export_from_ids(req.ids, fmt=fmt)
    mime = ("application/zip" if fmt == "zip"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return StreamingResponse(
        io.BytesIO(payload), media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="batch_reports.{fmt}"'},
    )


# --------------------------------------------------------------------------- #
# History + report download
# --------------------------------------------------------------------------- #
@app.get("/history")
def history(limit: int = 100) -> list[dict[str, Any]]:
    return storage.list_cases(limit=limit)


@app.get("/cases/{row_id}")
def get_case(row_id: str) -> dict[str, Any]:
    record = storage.get_case(row_id)
    if not record:
        raise HTTPException(404, "Case not found.")
    return record


@app.get("/cases/{row_id}/report.{fmt}")
def download_report(row_id: str, fmt: str) -> StreamingResponse:
    record = storage.get_case(row_id)
    if not record:
        raise HTTPException(404, "Case not found.")
    report = record["report"]
    exporters = {
        "pdf": (report_mod.to_pdf, "application/pdf"),
        "xlsx": (report_mod.to_excel,
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "json": (report_mod.to_json, "application/json"),
    }
    if fmt not in exporters:
        raise HTTPException(400, "Format must be pdf, xlsx, or json.")
    func, mime = exporters[fmt]
    payload = func(report)
    return StreamingResponse(
        io.BytesIO(payload), media_type=mime,
        headers={"Content-Disposition":
                 f'attachment; filename="{record.get("case_id") or row_id}.{fmt}"'},
    )
