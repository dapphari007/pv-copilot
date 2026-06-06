"""Retrieval-Augmented Generation over the FAERS case index.

Given a free-text adverse-event narrative (optionally enriched with extracted
entities), retrieve the most similar historical FAERS cases and format them as
grounding context for the LLM analysis step.
"""
from __future__ import annotations

from typing import Any

import config
from src import embeddings, vectordb
from src.chunking import chunk_text
from src.logging_config import get_logger

log = get_logger("rag")


def _build_query(narrative: str, entities: dict[str, Any] | None) -> str:
    """Combine the narrative with key entities to sharpen the retrieval query."""
    parts = [narrative.strip()]
    if entities:
        if entities.get("drug"):
            parts.append(f"Drug: {entities['drug']}")
        if entities.get("adverse_events"):
            parts.append("Events: " + ", ".join(entities["adverse_events"]))
        if entities.get("indication"):
            parts.append(f"Indication: {entities['indication']}")
    return " ".join(p for p in parts if p)


def retrieve_similar_cases(
    narrative: str,
    entities: dict[str, Any] | None = None,
    top_k: int | None = None,
    model_key: str | None = None,
    backend: str | None = None,
) -> list[dict[str, Any]]:
    """Return similar historical FAERS cases for the given narrative."""
    model_key = model_key or config.DEFAULT_MODEL_KEY
    if not vectordb.index_exists(model_key, backend=backend):
        log.info("No index for model=%s backend=%s; skipping retrieval.",
                 model_key, backend)
        return []
    # For long documents, embed the first chunk (the lead narrative) as the query.
    query_text = _build_query(narrative, entities)
    chunks = chunk_text(query_text)
    query_text = chunks[0] if chunks else query_text

    vector = embeddings.embed_query(query_text, model_key=model_key)
    results = vectordb.search(vector, model_key, top_k=top_k or config.TOP_K,
                              backend=backend)
    log.info("Retrieved %d cases (model=%s, backend=%s)", len(results),
             model_key, backend or "default")
    return results


def format_context(cases: list[dict[str, Any]]) -> str:
    """Render retrieved cases as a compact, citable context block."""
    if not cases:
        return "No similar historical cases were retrieved."
    lines: list[str] = []
    for i, case in enumerate(cases, start=1):
        sim = case.get("similarity", 0.0)
        lines.append(
            f"[Case {i} | id={case.get('primaryid', '?')} | "
            f"similarity={sim:.2f}]\n{case.get('narrative', '').strip()}"
        )
    return "\n\n".join(lines)
