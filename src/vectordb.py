"""Vector-store dispatcher — routes to the FAISS or Milvus backend.

The active backend is resolved from runtime settings (Settings page) but can be
overridden per call. This keeps ``rag.py`` and the API agnostic of which vector
database is in use.
"""
from __future__ import annotations

from typing import Any

import numpy as np

import config
from src import milvus_store, vector_store
from src.logging_config import get_logger
from src.settings_store import get as get_setting

log = get_logger("vectordb")


def _resolve(backend: str | None) -> str:
    backend = backend or get_setting("vector_backend") or config.DEFAULT_VECTOR_BACKEND
    if backend not in config.VECTOR_BACKENDS:
        log.warning("Unknown vector backend '%s'; using faiss.", backend)
        return "faiss"
    return backend


def index_exists(model_key: str, backend: str | None = None) -> bool:
    backend = _resolve(backend)
    if backend == "milvus":
        return milvus_store.index_exists(model_key)
    return vector_store.index_exists(model_key)


def search(query_vector: np.ndarray, model_key: str, top_k: int | None = None,
           backend: str | None = None) -> list[dict[str, Any]]:
    backend = _resolve(backend)
    if backend == "milvus":
        return milvus_store.search(query_vector, model_key, top_k=top_k)
    return vector_store.search(query_vector, model_key, top_k=top_k)


def available_models(backend: str | None = None) -> list[str]:
    """Embedding-model keys that have a built index in the active backend."""
    backend = _resolve(backend)
    if backend == "milvus":
        return [k for k in config.EMBEDDING_MODELS if milvus_store.index_exists(k)]
    return vector_store.available_models()


def backend_status() -> dict[str, Any]:
    """Diagnostic summary of both backends for the Settings/diagnostics views."""
    return {
        "active": _resolve(None),
        "faiss_models": vector_store.available_models(),
        "milvus_installed": milvus_store.available(),
        "milvus_models": [k for k in config.EMBEDDING_MODELS
                          if milvus_store.available() and milvus_store.index_exists(k)],
    }
