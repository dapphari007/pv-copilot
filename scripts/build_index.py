"""One-time build of the FAERS RAG artefacts.

Steps:
  1. Join the FAERS ASCII tables into per-case narratives.
  2. Build drug/reaction vocabularies for the offline extractor.
  3. Embed every case narrative and store vectors in a FAISS index.
  4. Persist case metadata (aligned to the index) for retrieval/display.

Usage:
    python scripts/build_index.py            # full dataset (~397K cases)
    MAX_CASES=5000 python scripts/build_index.py   # quick smoke test
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running as `python scripts/build_index.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src import embeddings, vector_store  # noqa: E402
from src.data_loader import build_case_frame  # noqa: E402
from src.dictionaries import save_vocabularies  # noqa: E402

# Columns persisted for retrieval display / report seeding.
META_COLUMNS = [
    "caseid", "narrative", "suspect_drug", "all_drugs", "reactions",
    "indications", "outcome_codes", "age_display", "sex_display",
    "weight_display", "seriousness", "occr_country", "event_dt",
]


def main() -> None:
    t0 = time.time()
    model_key = config.DEFAULT_MODEL_KEY
    if model_key not in config.EMBEDDING_MODELS:
        raise SystemExit(
            f"Unknown EMBED_MODEL_KEY='{model_key}'. "
            f"Choose one of: {', '.join(config.EMBEDDING_MODELS)}"
        )
    model_info = config.EMBEDDING_MODELS[model_key]
    max_cases = config.MAX_CASES
    scope = "FULL dataset" if max_cases == 0 else f"first {max_cases:,} cases"
    print(f"Embedding model: {model_key} -> {model_info['model_id']} "
          f"({model_info['dim']}d)")
    print(f"[1/4] Loading & joining FAERS tables ({scope}) ...", flush=True)
    cases = build_case_frame(max_cases=max_cases)
    print(f"      -> {len(cases):,} cases assembled in {time.time() - t0:.1f}s")

    print("[2/4] Building drug/reaction vocabularies ...", flush=True)
    drug_path, reac_path = save_vocabularies()
    print(f"      -> {drug_path.name}, {reac_path.name}")

    print("[3/4] Embedding case narratives (this is the slow step) ...", flush=True)
    narratives = cases["narrative"].tolist()
    t1 = time.time()
    vectors = embeddings.embed_texts(narratives, model_key=model_key, show_progress=True)
    print(f"      -> {vectors.shape[0]:,} vectors x {vectors.shape[1]}d "
          f"in {time.time() - t1:.1f}s")

    print("[4/4] Building & saving FAISS index + metadata ...", flush=True)
    index = vector_store.build_index(vectors, dim=model_info["dim"])
    meta = cases.reset_index()[["primaryid"] + META_COLUMNS]
    vector_store.save_index(index, meta, model_key)
    print(f"      -> index: {config.index_path(model_key)}")
    print(f"      -> meta:  {config.meta_path(model_key)}")

    print(f"\nDone in {time.time() - t0:.1f}s. Indexed {len(cases):,} FAERS cases "
          f"with '{model_key}'.")


if __name__ == "__main__":
    main()
