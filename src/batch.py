"""Batch analysis of many adverse-event cases (text or uploaded files).

Processes a list of cases concurrently (LLM/IO-bound, so a small thread pool
gives a big speedup) through the shared ``pipeline.run_analysis``. Each case is
persisted like a normal run, and the per-case result (or error) is returned so
the UI can render a results table and offer per-report + combined downloads.
"""
from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import config
from src import report as report_mod, storage
from src.documents import read_document
from src.logging_config import get_logger
from src.pipeline import run_analysis
from src.settings_store import load_settings

log = get_logger("batch")

# LLM calls are I/O-bound; keep concurrency modest to respect Groq rate limits.
MAX_WORKERS = int(getattr(config, "BATCH_WORKERS", 0) or 4)


class BatchItem:
    """One unit of batch work: free text and/or an uploaded file."""

    def __init__(self, text: str = "", file_name: str | None = None,
                 file_bytes: bytes | None = None, case_id: str = ""):
        self.text = (text or "").strip()
        self.file_name = file_name
        self.file_bytes = file_bytes
        self.case_id = case_id

    def resolve_text(self) -> tuple[str, str | None, str | None]:
        """Return (text, file_path, file_name) — reading/storing the file if given."""
        if self.file_bytes is not None and self.file_name:
            text = read_document(self.file_bytes, self.file_name).strip()
            path = storage.save_upload(self.file_bytes, self.file_name)
            return text, path, self.file_name
        return self.text, None, None


def run_batch(
    items: list[BatchItem],
    settings: dict[str, Any] | None = None,
    report_date: str = "",
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Analyze all items concurrently; returns a result dict per item (input order)."""
    settings = settings or load_settings()
    results: list[dict[str, Any] | None] = [None] * len(items)
    done = 0

    def _work(idx: int, item: BatchItem) -> dict[str, Any]:
        text, file_path, file_name = item.resolve_text()
        label = item.case_id or file_name or f"case-{idx + 1}"
        if not text:
            return {"index": idx, "label": label, "ok": False,
                    "error": "No text extracted from this item."}
        res = run_analysis(
            text, case_id=item.case_id or f"PV-BATCH-{idx + 1:03d}",
            report_date=report_date,
            source="upload" if file_name else "manual",
            file_path=file_path, file_name=file_name,
            source_documents=[file_name] if file_name else ["Batch text input"],
            settings=settings,
        )
        a = res["analysis"]
        return {
            "index": idx, "label": label, "ok": True, "id": res["id"],
            "case_id": res["report"]["case_information"]["Case ID"],
            "file_name": file_name, "drug": res["entities"].get("drug", ""),
            "all_drugs": res["entities"].get("all_drugs", []),
            "seriousness": a.get("seriousness", ""), "causality": a.get("causality", ""),
            "confidence": a.get("confidence_score", 0.0),
            "events": res["entities"].get("adverse_events", []),
        }

    log.info("Batch start: %d items (workers=%d)", len(items), MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_work, i, it): i for i, it in enumerate(items)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception as exc:  # noqa: BLE001 - surface per-item failures
                log.exception("Batch item %d failed", i)
                results[i] = {"index": i, "ok": False, "error": str(exc),
                              "label": items[i].case_id or f"case-{i + 1}"}
            done += 1
            if progress:
                progress(done, len(items))
    log.info("Batch done: %d/%d ok", sum(1 for r in results if r and r.get("ok")), len(items))
    return [r for r in results if r is not None]


def summary_excel(results: list[dict[str, Any]]) -> bytes:
    """One-row-per-case summary spreadsheet for a batch."""
    import pandas as pd

    rows = [{
        "Case ID": r.get("case_id", ""), "Label": r.get("label", ""),
        "File": r.get("file_name") or "manual", "Drug": r.get("drug", ""),
        "All Drugs": ", ".join(r.get("all_drugs", [])),
        "Adverse Events": ", ".join(r.get("events", [])),
        "Seriousness": r.get("seriousness", ""), "Causality": r.get("causality", ""),
        "Confidence": r.get("confidence", ""),
        "Status": "OK" if r.get("ok") else f"ERROR: {r.get('error', '')}",
    } for r in results]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Batch Summary", index=False)
    return buffer.getvalue()


def _result_from_stored(record: dict[str, Any]) -> dict[str, Any]:
    a, e = record.get("analysis", {}), record.get("entities", {})
    return {
        "ok": True, "id": record["id"], "case_id": record.get("case_id", ""),
        "label": record.get("case_id", record["id"][:8]),
        "file_name": record.get("file_name"), "drug": e.get("drug", ""),
        "all_drugs": e.get("all_drugs", []), "events": e.get("adverse_events", []),
        "seriousness": a.get("seriousness", ""), "causality": a.get("causality", ""),
        "confidence": a.get("confidence_score", 0.0),
    }


def export_from_ids(ids: list[str], fmt: str = "zip") -> bytes:
    """Build a combined export (zip of PDFs or summary xlsx) from stored case ids."""
    results = [_result_from_stored(r) for i in ids if (r := storage.get_case(i))]
    return summary_excel(results) if fmt == "xlsx" else reports_zip(results)


def reports_zip(results: list[dict[str, Any]]) -> bytes:
    """Zip of individual PDF reports for every successful case in the batch."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("batch_summary.xlsx", summary_excel(results))
        for r in results:
            if not r.get("ok") or not r.get("id"):
                continue
            record = storage.get_case(r["id"])
            if not record:
                continue
            name = (r.get("case_id") or r["id"][:8]).replace("/", "_")
            zf.writestr(f"{name}.pdf", report_mod.to_pdf(record["report"]))
    return buffer.getvalue()
