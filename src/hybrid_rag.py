"""LangChain-style Hybrid RAG over the FAERS FAISS index.

Pipeline (per PRD): query -> entity extraction -> keyword search + vector search
-> weighted hybrid merge (keyword 40% / vector 60%) -> MMR re-ranking -> Top-5,
excluding the current case. Keyword scoring runs over a vector candidate pool for
speed (no separate 397K BM25 index needed at query time).
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np

from src import embeddings, vectordb
from src.logging_config import get_logger

log = get_logger("hybrid_rag")

KW_WEIGHT = 0.40
VEC_WEIGHT = 0.60
POOL = 60          # vector candidates to re-rank
MMR_LAMBDA = 0.7   # relevance vs diversity

_TOKEN = re.compile(r"[a-z0-9]+")


def _terms(query: str, entities: dict[str, Any] | None) -> list[str]:
    terms = set(_TOKEN.findall(query.lower()))
    if entities:
        for d in entities.get("drugs", []):
            terms.update(_TOKEN.findall(str(d.get("name", "")).lower()))
        if entities.get("suspected_drug"):
            terms.update(_TOKEN.findall(entities["suspected_drug"].lower()))
        for ev in entities.get("adverse_events", []):
            terms.update(_TOKEN.findall(ev.lower()))
    return [t for t in terms if len(t) >= 3]


def _keyword_score(text: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    tokens = _TOKEN.findall(text.lower())
    if not tokens:
        return 0.0
    counts = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    score = sum(1.0 + np.log1p(counts.get(t, 0)) for t in terms if t in counts)
    return score / (len(terms) ** 0.5)


def _mmr(candidates: list[dict], vecs: np.ndarray, top_k: int) -> list[dict]:
    """Maximal Marginal Relevance selection for diversity."""
    if not candidates:
        return []
    rel = np.array([c["hybrid_score"] for c in candidates])
    selected: list[int] = []
    remaining = list(range(len(candidates)))
    while remaining and len(selected) < top_k:
        if not selected:
            best = int(remaining[int(np.argmax(rel[remaining]))])
        else:
            best, best_val = remaining[0], -1e9
            for i in remaining:
                div = max(float(vecs[i] @ vecs[j]) for j in selected)
                val = MMR_LAMBDA * rel[i] - (1 - MMR_LAMBDA) * div
                if val > best_val:
                    best, best_val = i, val
        selected.append(best)
        remaining.remove(best)
    return [candidates[i] for i in selected]


def hybrid_search(
    query: str,
    entities: dict[str, Any] | None = None,
    model_key: str = "minilm",
    backend: str = "faiss",
    top_k: int = 5,
    exclude_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return Top-K hybrid-ranked similar FAERS cases (current case excluded)."""
    exclude_ids = {str(x) for x in (exclude_ids or set())}
    if not vectordb.index_exists(model_key, backend=backend):
        log.warning("No %s/%s index — hybrid retrieval skipped.", backend, model_key)
        return []

    qvec = embeddings.embed_query(query, model_key)
    pool = vectordb.search(qvec, model_key, top_k=POOL, backend=backend)
    pool = [c for c in pool if str(c.get("primaryid", "")) not in exclude_ids]
    if not pool:
        return []

    terms = _terms(query, entities)
    narratives = [c.get("narrative", "") for c in pool]
    cand_vecs = embeddings.embed_texts(narratives, model_key=model_key)  # normalised

    kw_raw = [_keyword_score(n, terms) for n in narratives]
    max_kw = max(kw_raw) or 1.0
    for c, kw, vec in zip(pool, kw_raw, cand_vecs):
        c["vec_score"] = max(0.0, float(c.get("similarity", 0.0)))
        c["kw_score"] = kw / max_kw
        c["hybrid_score"] = VEC_WEIGHT * c["vec_score"] + KW_WEIGHT * c["kw_score"]

    ranked = _mmr(pool, cand_vecs, top_k)

    sus = (entities or {}).get("suspected_drug", "").lower()
    events = [e.lower() for e in (entities or {}).get("adverse_events", [])]
    results = []
    for c in ranked:
        narr = c.get("narrative", "")
        nlow = narr.lower()
        results.append({
            "case_id": str(c.get("primaryid", "")),
            "primaryid": str(c.get("primaryid", "")),
            "similarity": round(c["hybrid_score"], 3),
            "vector_score": round(c["vec_score"], 3),
            "keyword_score": round(c["kw_score"], 3),
            "narrative": narr,
            "snippet": narr[:240] + ("…" if len(narr) > 240 else ""),
            "reaction_match": [e for e in events if e and e in nlow],
            "drug_match": bool(sus and sus in nlow),
            "suspect_drug": c.get("suspect_drug", ""),
            "seriousness": c.get("seriousness", ""),
        })
    log.info("Hybrid retrieval -> %d results (pool=%d, kw=%.0f%%/vec=%.0f%%)",
             len(results), len(pool), KW_WEIGHT * 100, VEC_WEIGHT * 100)
    return results
