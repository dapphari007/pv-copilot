"""Runtime-editable application settings (persisted to ``data/settings.json``).

The Streamlit **Settings page** writes here; the analyze pipeline, FastAPI
backend, and other pages read here. Values fall back to ``config`` defaults when
the file is missing or a key is absent.
"""
from __future__ import annotations

import json
from typing import Any

import config
from src.logging_config import get_logger

log = get_logger("settings")

_DEFAULTS: dict[str, Any] = {
    "vector_backend": config.DEFAULT_VECTOR_BACKEND,  # "faiss" | "milvus"
    "embedding_model": config.DEFAULT_MODEL_KEY,      # "minilm" | "biobert"
    "rag_engine": "Native",                           # "Native" | "LangChain"
    "top_k": config.TOP_K,
}


def load_settings() -> dict[str, Any]:
    """Return current settings, merged over defaults."""
    settings = dict(_DEFAULTS)
    if config.SETTINGS_PATH.exists():
        try:
            settings.update(json.loads(config.SETTINGS_PATH.read_text("utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read settings.json (%s); using defaults.", exc)
    return settings


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge ``updates`` into the stored settings and persist them."""
    settings = load_settings()
    settings.update({k: v for k, v in updates.items() if k in _DEFAULTS})
    config.SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    log.info("Settings updated: %s", updates)
    return settings


def get(key: str) -> Any:
    return load_settings().get(key, _DEFAULTS.get(key))
