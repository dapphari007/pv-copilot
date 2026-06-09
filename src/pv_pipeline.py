"""Multi-patient PV processing pipeline.

For an uploaded document (or batch), detect every distinct patient case, run
hybrid retrieval + analysis + report generation per case, and persist each under
a single ``upload_id`` so the dashboard reflects the CURRENT upload only.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src import case_detection, hybrid_rag, pv_analysis, pv_report, pv_storage
from src.logging_config import get_logger
from src.settings_store import load_settings

log = get_logger("analysis")

MAX_WORKERS = 6  # concurrent per-case processing (LLM/IO bound)


def _process_case(case: dict[str, Any], idx: int, upload_id: str, file_name: str | None,
                  settings: dict[str, Any], report_date: str) -> dict[str, Any]:
    model_key = settings.get("embedding_model", "minilm")
    backend = "faiss"  # Milvus is added later on this branch
    top_k = int(settings.get("top_k", 5))

    query = case.get("_segment_text", "") or " ".join(
        case.get("adverse_events", []) + [case.get("suspected_drug", "")])
    retrieved = hybrid_rag.hybrid_search(
        query, entities=case, model_key=model_key, backend=backend, top_k=top_k,
        exclude_ids={case.get("case_id", "")})

    analysis = pv_analysis.analyze(case, retrieved)
    case_id = case.get("case_id") or f"{upload_id[:6].upper()}-{idx + 1:03d}"
    report = pv_report.build_report(
        case, analysis, retrieved, case_id=case_id, report_date=report_date,
        source_documents=[file_name] if file_name else ["Patient narrative"])

    row_id = pv_storage.save_case(upload_id, case, analysis, report, retrieved, file_name)
    return {
        "id": row_id, "case_id": case_id, "patient_id": case.get("patient_id", ""),
        "suspected_drug": case.get("suspected_drug", ""),
        "all_drugs": [d["name"] for d in case.get("drugs", [])],
        "seriousness": analysis.get("seriousness", ""),
        "causality": analysis.get("causality", ""),
        "outcome": case.get("outcome", ""),
        "report": report, "analysis": analysis, "case": case, "retrieved": retrieved,
    }


def process_upload(documents: list[tuple[str, str | None]],
                   settings: dict[str, Any] | None = None,
                   report_date: str = "") -> dict[str, Any]:
    """Process one or more documents as a single upload batch.

    ``documents`` is a list of (text, file_name). Returns current-upload stats and
    every generated patient report.
    """
    settings = settings or load_settings()
    upload_id = pv_storage.new_upload_id()
    log.info("Upload %s: %d document(s)", upload_id, len(documents))

    work: list[tuple[dict[str, Any], str | None]] = []
    for text, file_name in documents:
        for case in case_detection.detect_cases(text):
            work.append((case, file_name))

    results: list[dict[str, Any]] = [None] * len(work)  # type: ignore[list-item]
    if work:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(work))) as pool:
            futures = {
                pool.submit(_process_case, case, i, upload_id, fn, settings, report_date): i
                for i, (case, fn) in enumerate(work)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    results[i] = fut.result()
                except Exception as exc:  # noqa: BLE001
                    log.exception("Case %d failed: %s", i, exc)
    results = [r for r in results if r is not None]

    serious = sum(1 for r in results if r["seriousness"] == "Serious")
    summary = {
        "upload_id": upload_id,
        "documents_processed": len(documents),
        "cases_found": len(results),
        "reports_generated": len(results),
        "serious_cases": serious,
        "non_serious_cases": len(results) - serious,
        "cases": results,
    }
    log.info("Upload %s done: %d case(s), %d serious", upload_id, len(results), serious)
    return summary
