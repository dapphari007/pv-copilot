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
from src import extraction, report as report_mod, storage, vectordb
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
    text = _read_document(data, file.filename or "upload")
    if not text.strip():
        raise HTTPException(422, "Could not extract text from the uploaded file.")
    stored_path = storage.save_upload(data, file.filename or "upload")
    return run_analysis(
        text, case_id=case_id, report_date=report_date, source="upload",
        file_path=stored_path, file_name=file.filename,
        source_documents=[file.filename or "uploaded document"],
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


def _read_document(data: bytes, name: str) -> str:
    """Extract text from uploaded TXT/PDF/DOCX bytes (logic kept tiny here)."""
    lower = name.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if lower.endswith(".docx"):
        import docx
        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    return data.decode("utf-8", errors="replace")
