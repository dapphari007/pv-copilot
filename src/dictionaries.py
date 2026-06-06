"""Drug and reaction vocabularies derived from the FAERS dataset itself.

These power the deterministic, offline entity-extraction fallback used when no
LLM key is configured. Building the vocab from the same data the RAG index is
built on keeps extraction consistent with retrieval.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import config
from src.data_loader import _READ_KW, _faers_path


def _normalise(values: pd.Series, min_len: int = 3) -> list[str]:
    cleaned = (
        values.str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .loc[lambda s: s.str.len() >= min_len]
    )
    return sorted({v for v in cleaned if v and not v.isdigit()})


def build_vocabularies() -> tuple[list[str], list[str]]:
    """Extract distinct drug names and reaction preferred terms from FAERS."""
    drug = pd.read_csv(
        _faers_path("DRUG"), usecols=["drugname", "prod_ai"], **_READ_KW
    )
    drug_names = _normalise(pd.concat([drug["drugname"], drug["prod_ai"]]))

    reac = pd.read_csv(_faers_path("REAC"), usecols=["pt"], **_READ_KW)
    reactions = _normalise(reac["pt"])
    return drug_names, reactions


def save_vocabularies() -> tuple[Path, Path]:
    drugs, reactions = build_vocabularies()
    config.DRUG_VOCAB_PATH.write_text("\n".join(drugs), encoding="utf-8")
    config.REAC_VOCAB_PATH.write_text("\n".join(reactions), encoding="utf-8")
    return config.DRUG_VOCAB_PATH, config.REAC_VOCAB_PATH


def load_vocabularies() -> tuple[list[str], list[str]]:
    """Load cached vocab files; returns empty lists if they have not been built."""
    drugs: list[str] = []
    reactions: list[str] = []
    if config.DRUG_VOCAB_PATH.exists():
        drugs = config.DRUG_VOCAB_PATH.read_text(encoding="utf-8").splitlines()
    if config.REAC_VOCAB_PATH.exists():
        reactions = config.REAC_VOCAB_PATH.read_text(encoding="utf-8").splitlines()
    return drugs, reactions
