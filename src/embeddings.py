"""Sentence-transformers embedding wrapper with lazy, cached model loading."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

import config


@lru_cache(maxsize=2)
def get_model(model_key: str | None = None):
    """Load (and cache) the embedding model for the given registry key."""
    from src import _sklearn_shim  # noqa: F401  (must precede sentence-transformers)
    from sentence_transformers import SentenceTransformer

    model_key = model_key or config.DEFAULT_MODEL_KEY
    return SentenceTransformer(config.model_id(model_key))


def embed_texts(
    texts: list[str],
    model_key: str | None = None,
    batch_size: int | None = None,
    show_progress: bool = False,
) -> np.ndarray:
    """Embed a list of texts into L2-normalised float32 vectors (cosine-ready)."""
    model_key = model_key or config.DEFAULT_MODEL_KEY
    if not texts:
        return np.zeros((0, config.model_dim(model_key)), dtype="float32")
    model = get_model(model_key)
    vectors = model.encode(
        texts,
        batch_size=batch_size or config.EMBEDDING_BATCH_SIZE,
        show_progress_bar=show_progress,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return vectors.astype("float32")


@lru_cache(maxsize=512)
def _embed_query_cached(text: str, model_key: str | None) -> np.ndarray:
    return embed_texts([text], model_key=model_key)


def embed_query(text: str, model_key: str | None = None) -> np.ndarray:
    """Embed a single query, returning a (1, dim) array (cached to avoid re-embeds)."""
    return _embed_query_cached(text, model_key)
