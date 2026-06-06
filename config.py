"""Central configuration for the Pharmacovigilance AI Copilot.

All tunables (paths, model names, API keys) are resolved here so the rest of
the codebase imports a single source of truth. Environment variables override
defaults, and a local .env file is loaded automatically when present.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars still work without it.
    pass


# --------------------------------------------------------------------------- #
# Filesystem layout
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent
FAERS_DIR = PROJECT_ROOT / "faers_ascii_2026q1" / "ASCII"
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Quarter tag used in the FAERS filenames (e.g. DEMO26Q1.txt).
FAERS_QUARTER = os.getenv("FAERS_QUARTER", "26Q1")

# Generated artefacts produced by scripts/build_index.py
CORPUS_PATH = DATA_DIR / "faers_corpus.parquet"  # raw per-case narrative text
DRUG_VOCAB_PATH = DATA_DIR / "drug_vocab.txt"
REAC_VOCAB_PATH = DATA_DIR / "reaction_vocab.txt"


# --------------------------------------------------------------------------- #
# Embeddings / vector store
# --------------------------------------------------------------------------- #
# Registry of selectable embedding models. Each builds its own FAISS index so
# the two can coexist and be switched from the UI. The model used to BUILD an
# index must also be used to QUERY it — vectors are not cross-compatible.
EMBEDDING_MODELS: dict[str, dict] = {
    "minilm": {
        "label": "all-MiniLM-L6-v2 (fast · general)",
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
    },
    "biobert": {
        "label": "BioBERT / S-BioBert (biomedical · slower)",
        "model_id": os.getenv("BIOBERT_MODEL", "pritamdeka/S-BioBert-snli-multinli-stsb"),
        "dim": 768,
    },
}
# Default model key used by the CLI build script and as the UI default.
DEFAULT_MODEL_KEY = os.getenv("EMBED_MODEL_KEY", "minilm")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "256"))


def index_path(model_key: str) -> Path:
    """FAISS index path for a given embedding-model key."""
    return DATA_DIR / f"faers_{model_key}.index"


def meta_path(model_key: str) -> Path:
    """Per-case metadata path (aligned to that model's index)."""
    return DATA_DIR / f"faers_{model_key}_meta.parquet"


def model_id(model_key: str) -> str:
    return EMBEDDING_MODELS[model_key]["model_id"]


def model_dim(model_key: str) -> int:
    return EMBEDDING_MODELS[model_key]["dim"]

# 0 (default) means index the full dataset; a positive value caps the case count
# which is handy for quick local smoke tests.
MAX_CASES = int(os.getenv("MAX_CASES", "0"))

# Chunking parameters for long uploaded narratives / documents.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

# Number of similar historical cases to retrieve for RAG context.
TOP_K = int(os.getenv("TOP_K", "5"))


# --------------------------------------------------------------------------- #
# LLM backend (Groq — OpenAI-compatible chat completions)
# --------------------------------------------------------------------------- #
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1500"))


def llm_available() -> bool:
    """True when a Groq API key is configured; otherwise rule-based fallback is used."""
    return bool(GROQ_API_KEY)


# --------------------------------------------------------------------------- #
# FAERS reference code maps
# --------------------------------------------------------------------------- #
# Patient outcome codes (OUTC table). The "serious" subset follows ICH E2A.
OUTCOME_CODES = {
    "DE": "Death",
    "LT": "Life-Threatening",
    "HO": "Hospitalization - Initial or Prolonged",
    "DS": "Disability",
    "CA": "Congenital Anomaly",
    "RI": "Required Intervention to Prevent Permanent Impairment/Damage",
    "OT": "Other Serious (Important Medical Event)",
}
SERIOUS_OUTCOME_CODES = {"DE", "LT", "HO", "DS", "CA", "RI"}

# Drug role codes (DRUG table).
ROLE_CODES = {
    "PS": "Primary Suspect",
    "SS": "Secondary Suspect",
    "C": "Concomitant",
    "I": "Interacting",
}

# Report type codes (DEMO table).
REPORT_CODES = {
    "EXP": "Expedited",
    "PER": "Periodic",
    "DIR": "Direct",
    "BSN": "Non-expedited",
}
