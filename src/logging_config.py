"""Central logging — per-area log files plus a shared application.log.

Per the rebuild PRD, modules log to dedicated files:
  application.log · upload.log · vector_db.log · retrieval.log ·
  analysis.log · report_generation.log · auth.log
Format: ``timestamp | LEVEL | module | message``. No print statements anywhere.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

# logger-name -> dedicated log file (everything also goes to application.log)
_AREA_FILES = {
    "upload": "upload.log",
    "vectordb": "vector_db.log",
    "vector_store": "vector_db.log",
    "milvus": "vector_db.log",
    "retrieval": "retrieval.log",
    "rag": "retrieval.log",
    "hybrid_rag": "retrieval.log",
    "analysis": "analysis.log",
    "extraction": "analysis.log",
    "case_detection": "analysis.log",
    "report": "report_generation.log",
    "auth": "auth.log",
}

_configured: set[str] = set()
_shared_handler: RotatingFileHandler | None = None


def _file_handler(filename: str) -> RotatingFileHandler:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        _LOG_DIR / filename, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    return handler


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to application.log + its area file + console."""
    global _shared_handler
    logger = logging.getLogger(f"pv.{name}")
    if name in _configured:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    if _shared_handler is None:
        _shared_handler = _file_handler("application.log")
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        logging.getLogger("pv").addHandler(console)
    logger.addHandler(_shared_handler)

    area_file = _AREA_FILES.get(name)
    if area_file:
        logger.addHandler(_file_handler(area_file))

    # also send to the root pv console handler
    logger.addHandler(logging.getLogger("pv").handlers[0])
    _configured.add(name)
    return logger
