"""Migrate an existing FAISS index into Milvus — no re-embedding required.

Reconstructs the stored vectors straight from the FAISS index and re-uses the
aligned metadata, then ingests both into a Milvus collection. Much faster than
rebuilding, since embedding is skipped.

Usage (Milvus must be running — see docker-compose.milvus.yml):
    python scripts/faiss_to_milvus.py                      # minilm
    $env:EMBED_MODEL_KEY="biobert"; python scripts/faiss_to_milvus.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src import milvus_store, vector_store  # noqa: E402


def main() -> None:
    model_key = config.DEFAULT_MODEL_KEY
    if not vector_store.index_exists(model_key):
        raise SystemExit(
            f"No FAISS index for '{model_key}'. Build it first with "
            f"`EMBED_MODEL_KEY={model_key} python scripts/build_index.py`."
        )
    if not milvus_store.available():
        raise SystemExit("pymilvus is not installed.")

    t0 = time.time()
    print(f"[1/3] Loading FAISS index + metadata ('{model_key}') ...", flush=True)
    index = vector_store.load_index(model_key)
    meta = vector_store.load_meta(model_key)
    n = index.ntotal
    print(f"      -> {n:,} vectors")

    print("[2/3] Reconstructing vectors from FAISS ...", flush=True)
    vectors = index.reconstruct_n(0, n)
    print(f"      -> array {vectors.shape}")

    print(f"[3/3] Ingesting into Milvus ({config.MILVUS_URI}) ...", flush=True)
    milvus_store.ingest(vectors, meta, model_key)
    print(f"\nDone in {time.time() - t0:.1f}s. Collection "
          f"'{config.milvus_collection(model_key)}' ready with {n:,} vectors.")


if __name__ == "__main__":
    main()
