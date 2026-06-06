"""Milvus vector-store backend (alternative to FAISS).

Uses ``pymilvus.MilvusClient`` against a Milvus server (set ``MILVUS_URI``).
On Windows, run Milvus standalone via Docker:

    docker run -d --name milvus-standalone -p 19530:19530 \\
        milvusdb/milvus:latest milvus run standalone

Each embedding model maps to its own collection (``faers_<model_key>``).
``ingest`` is called by ``scripts/build_index.py`` when ``VECTOR_BACKEND=milvus``.
Cosine similarity is used (vectors are pre-normalised, so IP == cosine).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

import config
from src.logging_config import get_logger

log = get_logger("milvus")

# Scalar metadata fields mirrored into Milvus for display after retrieval.
_META_FIELDS = [
    "primaryid", "narrative", "suspect_drug", "reactions", "seriousness",
    "age_display", "sex_display", "occr_country",
]


def available() -> bool:
    try:
        import pymilvus  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _client():
    if not available():
        raise RuntimeError("pymilvus is not installed.")
    from pymilvus import MilvusClient

    kwargs: dict[str, Any] = {"uri": config.MILVUS_URI}
    if config.MILVUS_TOKEN:
        kwargs["token"] = config.MILVUS_TOKEN
    log.info("Connecting to Milvus at %s", config.MILVUS_URI)
    return MilvusClient(**kwargs)


def index_exists(model_key: str) -> bool:
    """True when the collection for this model exists and is reachable."""
    if not available():
        return False
    try:
        return _client().has_collection(config.milvus_collection(model_key))
    except Exception as exc:  # server unreachable, etc.
        log.warning("Milvus check failed: %s", exc)
        return False


def ingest(vectors: np.ndarray, meta, model_key: str) -> None:
    """(Re)create the collection for ``model_key`` and insert all vectors + meta."""
    from pymilvus import DataType

    client = _client()
    name = config.milvus_collection(model_key)
    if client.has_collection(name):
        client.drop_collection(name)

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("pk", DataType.INT64, is_primary=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=config.model_dim(model_key))
    for field in _META_FIELDS:
        schema.add_field(field, DataType.VARCHAR, max_length=4096)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX",
                           metric_type="IP")
    client.create_collection(name, schema=schema, index_params=index_params)

    records = meta.to_dict("records")
    rows = []
    for i, (vec, rec) in enumerate(zip(vectors, records)):
        row = {"pk": i, "vector": vec.tolist()}
        for field in _META_FIELDS:
            row[field] = str(rec.get(field, ""))[:4000]
        rows.append(row)

    batch = 2000
    for start in range(0, len(rows), batch):
        client.insert(name, rows[start:start + batch])
        log.info("Milvus insert %d/%d", min(start + batch, len(rows)), len(rows))
    client.flush(name)
    log.info("Milvus collection '%s' ready (%d vectors)", name, len(rows))


def search(query_vector: np.ndarray, model_key: str,
           top_k: int | None = None) -> list[dict[str, Any]]:
    top_k = top_k or config.TOP_K
    if query_vector.ndim == 1:
        query_vector = query_vector.reshape(1, -1)
    client = _client()
    name = config.milvus_collection(model_key)
    hits = client.search(
        name, data=query_vector.tolist(), limit=top_k,
        output_fields=_META_FIELDS, search_params={"metric_type": "IP"},
    )
    results: list[dict[str, Any]] = []
    for hit in hits[0]:
        entity = hit.get("entity", {})
        record = {field: entity.get(field, "") for field in _META_FIELDS}
        record["similarity"] = float(hit.get("distance", 0.0))
        results.append(record)
    return results
