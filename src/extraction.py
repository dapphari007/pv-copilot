"""Pharmacovigilance entity extraction.

Two strategies share one output schema:

* :func:`extract_entities_llm` — Groq-powered structured extraction (preferred).
* :func:`extract_entities_rules` — deterministic dictionary + regex matcher that
  uses the FAERS-derived vocabularies, so the app works with no API key.

:func:`extract_entities` selects the best available strategy automatically.
"""
from __future__ import annotations

import re
from typing import Any

import config
from src import seriousness
from src.dictionaries import load_vocabularies

# Canonical entity schema returned by every extractor.
EMPTY_ENTITIES: dict[str, Any] = {
    "drug": "",
    "all_drugs": [],
    "adverse_events": [],
    "indication": "",
    "age": "",
    "gender": "",
    "weight": "",
    "medical_history": "",
    "dosage": "",
    "route": "",
    "therapy_start_date": "",
    "therapy_end_date": "",
    "event_start_date": "",
    "outcome": "",
    "severity": "",
    "action_taken": "",
    "seriousness": "",
}

_AGE_RE = re.compile(r"\b(\d{1,3})[\s-]*(?:year|yr|y/o|yo|years?)[\s-]*(?:old)?\b", re.I)
_GENDER_RE = re.compile(r"\b(male|female|man|woman|boy|girl|m/|f/)\b", re.I)
_DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|iu))\b", re.I)
_ROUTE_RE = re.compile(
    r"\b(oral|intravenous|iv|subcutaneous|intramuscular|im|topical|inhaled|"
    r"intravenously|orally)\b",
    re.I,
)
_WEIGHT_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*(kg|kilograms?|lbs?|pounds?)\b", re.I)
_SEVERITY_RE = re.compile(r"\b(mild|moderate|severe|life[- ]threatening|fatal)\b", re.I)
# Dates like 15-May-2026, 15 May 2026, 2026-05-15, 05/15/2026.
_DATE_RE = re.compile(
    r"\b(\d{1,2}[-/ ](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.I,
)
_ACTION_RULES: list[tuple[str, str]] = [
    (r"\b(discontinu|withdrawn|stopped|ceased)\b", "Drug Discontinued"),
    (r"\b(dose reduc|reduced dose)\b", "Dose Reduced"),
    (r"\b(dose increas)\b", "Dose Increased"),
    (r"\b(not changed|unchanged|continued)\b", "Dose Not Changed"),
]

_EXTRACTION_SYSTEM = (
    "You are a clinical pharmacovigilance entity-extraction engine. "
    "Extract structured drug-safety entities from the adverse-event text. "
    "Only use information present in the text; never invent values. "
    "Respond with a single JSON object and nothing else."
)

_EXTRACTION_TEMPLATE = """Extract the following fields from the adverse event text.
Return JSON with EXACTLY these keys:
- "drug": primary suspected drug name (string, "" if unknown)
- "all_drugs": list of all drug names mentioned
- "adverse_events": list of adverse events / reactions / symptoms
- "indication": reason the drug was taken (string)
- "age": patient age with unit if stated (string)
- "gender": "Male", "Female", or "" if unknown
- "weight": patient weight with unit if stated (string)
- "medical_history": relevant past medical history / comorbidities (string)
- "dosage": dose with unit if stated (string)
- "route": route of administration (string)
- "therapy_start_date": drug therapy start date if stated (string)
- "therapy_end_date": drug therapy end date if stated (string)
- "event_start_date": adverse event onset date if stated (string)
- "outcome": clinical outcome, e.g. hospitalization/recovered/death (string)
- "severity": event severity, e.g. "Mild", "Moderate", "Severe" (string)
- "action_taken": action taken with the drug, e.g. "Drug Discontinued", "Dose Reduced" (string)
- "seriousness": "Serious" or "Non-Serious" per ICH E2A criteria

Adverse event text:
\"\"\"{text}\"\"\""""


def extract_entities(text: str) -> dict[str, Any]:
    """Extract entities using the LLM when available, else the rule-based path."""
    if config.llm_available():
        try:
            return extract_entities_llm(text)
        except Exception:
            # Any LLM failure degrades gracefully to deterministic extraction.
            pass
    return extract_entities_rules(text)


def extract_entities_llm(text: str) -> dict[str, Any]:
    from src import llm

    data = llm.chat_json(_EXTRACTION_SYSTEM, _EXTRACTION_TEMPLATE.format(text=text))
    return _coerce(data, text)


def extract_entities_rules(text: str) -> dict[str, Any]:
    drug_vocab, reac_vocab = load_vocabularies()
    lower = (text or "").lower()

    drugs = _match_vocab(lower, drug_vocab, limit=10)
    events = _match_vocab(lower, reac_vocab, limit=15)

    age = ""
    if (m := _AGE_RE.search(text)):
        age = f"{m.group(1)} years"

    gender = ""
    if (m := _GENDER_RE.search(lower)):
        token = m.group(1).lower()
        gender = "Female" if token in {"female", "woman", "girl", "f/"} else "Male"

    dosage = m.group(1) if (m := _DOSE_RE.search(text)) else ""
    route = m.group(1).title() if (m := _ROUTE_RE.search(text)) else ""

    weight = ""
    if (m := _WEIGHT_RE.search(text)):
        weight = f"{m.group(1)} {m.group(2).lower()}"
    severity = m.group(1).title() if (m := _SEVERITY_RE.search(text)) else ""

    action_taken = next(
        (label for pattern, label in _ACTION_RULES if re.search(pattern, text, re.I)),
        "",
    )

    # Heuristically assign detected dates: first two -> therapy window, last -> event.
    dates = _DATE_RE.findall(text)
    therapy_start = dates[0] if len(dates) >= 1 else ""
    therapy_end = dates[1] if len(dates) >= 3 else ""
    event_start = dates[-1] if len(dates) >= 2 else ""

    serious = seriousness.assess_from_text(text)

    entities = dict(EMPTY_ENTITIES)
    entities.update(
        drug=drugs[0] if drugs else "",
        all_drugs=drugs,
        adverse_events=events,
        age=age,
        gender=gender,
        weight=weight,
        dosage=dosage,
        route=route,
        therapy_start_date=therapy_start,
        therapy_end_date=therapy_end,
        event_start_date=event_start,
        severity=severity,
        action_taken=action_taken,
        seriousness=serious["classification"],
    )
    return entities


def _match_vocab(lower_text: str, vocab: list[str], limit: int) -> list[str]:
    """Find vocabulary terms that appear as whole words/phrases in the text."""
    hits: list[str] = []
    seen: set[str] = set()
    for term in vocab:
        t = term.lower()
        if len(t) < 4:
            continue
        if re.search(rf"\b{re.escape(t)}\b", lower_text):
            if t not in seen:
                hits.append(term.title())
                seen.add(t)
        if len(hits) >= limit:
            break
    return hits


def _coerce(data: dict[str, Any], text: str) -> dict[str, Any]:
    """Normalise an LLM dict into the canonical schema with safe types."""
    entities = dict(EMPTY_ENTITIES)
    for key in entities:
        if key in data and data[key] is not None:
            entities[key] = data[key]

    def _as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [p.strip() for p in re.split(r"[;,]", value) if p.strip()]
        return []

    entities["all_drugs"] = _as_list(entities["all_drugs"])
    entities["adverse_events"] = _as_list(entities["adverse_events"])
    if not entities["drug"] and entities["all_drugs"]:
        entities["drug"] = entities["all_drugs"][0]
    if entities["drug"] and entities["drug"] not in entities["all_drugs"]:
        entities["all_drugs"].insert(0, entities["drug"])
    return entities
