"""FAISS-backed vector store over FAERS case narratives (multi-model aware).

Each embedding model gets its own index + metadata file (see ``config.index_path``).
Vectors are L2-normalised and stored in an inner-product index, so similarity
scores are cosine similarities in ``[-1, 1]``. Case metadata is held in a parquet
file whose row order is aligned 1:1 with the FAISS index.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

import config


def build_index(vectors: np.ndarray, dim: int):
    """Create a flat cosine (inner-product) FAISS index from normalised vectors."""
    import faiss

    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


def save_index(index, meta: pd.DataFrame, model_key: str) -> None:
    import faiss

    faiss.write_index(index, str(config.index_path(model_key)))
    meta.to_parquet(config.meta_path(model_key), index=False)


@lru_cache(maxsize=4)
def load_index(model_key: str):
    import faiss

    path = config.index_path(model_key)
    if not path.exists():
        raise FileNotFoundError(
            f"FAISS index not found at {path}. "
            f"Build it with `EMBED_MODEL_KEY={model_key} python scripts/build_index.py`."
        )
    return faiss.read_index(str(path))


@lru_cache(maxsize=4)
def load_meta(model_key: str) -> pd.DataFrame:
    path = config.meta_path(model_key)
    if not path.exists():
        raise FileNotFoundError(f"Case metadata not found at {path}.")
    return pd.read_parquet(path)


def index_exists(model_key: str) -> bool:
    return config.index_path(model_key).exists() and config.meta_path(model_key).exists()


def available_models() -> list[str]:
    """Registry keys whose index has actually been built."""
    return [key for key in config.EMBEDDING_MODELS if index_exists(key)]


def search(
    query_vector: np.ndarray, model_key: str, top_k: int | None = None
) -> list[dict[str, Any]]:
    """Return the ``top_k`` most similar cases (with cosine scores) for a model."""
    top_k = top_k or config.TOP_K
    index = load_index(model_key)
    meta = load_meta(model_key)
    if query_vector.ndim == 1:
        query_vector = query_vector.reshape(1, -1)
    scores, indices = index.search(query_vector.astype("float32"), top_k)

    results: list[dict[str, Any]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        record = meta.iloc[int(idx)].to_dict()
        record["similarity"] = float(score)
        results.append(record)
    return results
