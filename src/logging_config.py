"""Central logging configuration for the Pharmacovigilance AI Copilot.

Provides a single ``get_logger`` entry point used across the codebase, the
FastAPI backend, and the Streamlit UI. Logs go to both the console and a
rotating file under ``logs/``.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "pv_copilot.log"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("pv")
    root.setLevel(logging.INFO)
    root.propagate = False

    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(console)

        file_handler = RotatingFileHandler(
            _LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (e.g. ``get_logger("rag")`` -> ``pv.rag``)."""
    _configure()
    return logging.getLogger(f"pv.{name}")
