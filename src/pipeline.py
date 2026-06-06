"""End-to-end analysis orchestration shared by the API and the Streamlit UI.

One function, :func:`run_analysis`, runs the full flow:
extract -> retrieve (FAISS/Milvus) -> analyze (Native/LangChain) -> report,
then persists the run to SQLite. Both ``main.py`` (FastAPI) and the Streamlit
pages call this so business logic lives in exactly one place.
"""
from __future__ import annotations

from typing import Any

from src import analysis as analysis_mod
from src import extraction, rag, rag_langchain, report as report_mod, storage
from src.logging_config import get_logger
from src.settings_store import load_settings

log = get_logger("pipeline")


def run_analysis(
    narrative: str,
    *,
    case_id: str = "PV-DRAFT-0001",
    report_date: str = "",
    source: str = "manual",
    file_path: str | None = None,
    file_name: str | None = None,
    source_documents: list[str] | None = None,
    settings: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run the full PV pipeline and (optionally) persist it. Returns all artefacts."""
    settings = settings or load_settings()
    model_key = settings.get("embedding_model")
    backend = settings.get("vector_backend")
    engine = settings.get("rag_engine", "Native")
    log.info("Analyze start | model=%s backend=%s engine=%s source=%s",
             model_key, backend, engine, source)

    entities = extraction.extract_entities(narrative)

    if engine == "LangChain" and rag_langchain.langchain_available():
        lc = rag_langchain.analyze_case_langchain(
            narrative, entities, model_key=model_key, backend=backend)
        retrieved, analysis = lc["retrieved"], lc["analysis"]
    else:
        retrieved = rag.retrieve_similar_cases(
            narrative, entities, model_key=model_key, backend=backend)
        analysis = analysis_mod.analyze_case(narrative, entities, retrieved)

    report = report_mod.build_report(
        entities, analysis, case_id=case_id, report_date=report_date,
        retrieved_cases=retrieved, source_documents=source_documents,
    )

    row_id = None
    if persist:
        try:
            row_id = storage.save_case(
                prompt=narrative, entities=entities, analysis=analysis,
                report=report, source=source, file_path=file_path,
                file_name=file_name, settings=settings,
            )
        except Exception as exc:  # persistence must never break the response
            log.exception("Failed to persist case: %s", exc)

    log.info("Analyze done | serious=%s causality=%s retrieved=%d id=%s",
             analysis.get("seriousness"), analysis.get("causality"),
             len(retrieved), (row_id or "-")[:8])
    return {
        "id": row_id,
        "entities": entities,
        "retrieved": retrieved,
        "analysis": analysis,
        "report": report,
        "settings": settings,
    }
