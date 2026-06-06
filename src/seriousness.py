"""Rule-based seriousness assessment grounded in ICH E2A / FAERS OUTC codes.

Used both as the deterministic fallback and as a ground-truth cross-check on the
LLM's assessment. Seriousness is keyword-driven from the narrative when no
structured outcome codes are available.
"""
from __future__ import annotations

import re
from typing import Any

import config

# Narrative keyword patterns mapped to FAERS outcome codes.
_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"\b(died|death|fatal|deceased|passed away)\b", "DE"),
    (r"\b(life[- ]threatening|near fatal)\b", "LT"),
    (r"\b(hospitali[sz]ation|hospitali[sz]ed|admitted to hospital|inpatient)\b", "HO"),
    (r"\b(disab(led|ility)|permanent|incapacit)\b", "DS"),
    (r"\b(congenital|birth defect|fetal)\b", "CA"),
    (r"\b(intervention to prevent|required surgery|emergency)\b", "RI"),
]


def assess_from_codes(outcome_codes: list[str]) -> dict[str, Any]:
    """Assess seriousness from a list of FAERS OUTC codes (e.g. ['HO', 'OT'])."""
    codes = {c.strip().upper() for c in outcome_codes if c and c.strip()}
    serious = bool(codes & config.SERIOUS_OUTCOME_CODES)
    return _build(codes, serious)


def assess_from_text(text: str) -> dict[str, Any]:
    """Infer seriousness criteria from free-text narrative via keyword rules."""
    text = (text or "").lower()
    codes = {code for pattern, code in _KEYWORD_RULES if re.search(pattern, text)}
    serious = bool(codes & config.SERIOUS_OUTCOME_CODES)
    return _build(codes, serious)


def _build(codes: set[str], serious: bool) -> dict[str, Any]:
    return {
        "is_serious": serious,
        "classification": "Serious" if serious else "Non-Serious",
        "outcome_codes": sorted(codes),
        "criteria": {
            "Death": "DE" in codes,
            "Life Threatening": "LT" in codes,
            "Hospitalization": "HO" in codes,
            "Disability": "DS" in codes,
            "Congenital Anomaly": "CA" in codes,
            "Required Intervention": "RI" in codes,
        },
        "decoded_outcomes": [
            config.OUTCOME_CODES.get(c, c) for c in sorted(codes)
        ],
    }
