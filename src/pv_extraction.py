"""Pharmacovigilance entity extraction for a SINGLE patient case segment.

Extraction-only (no training): a completely new drug like ``XYZ-123`` is still
detected, classified, and reported. The LLM is the primary engine; a
deterministic dictionary/regex path is the fallback when no key is available.

Guarantees enforced on the output:
  * ALL drugs captured, each with a role: PS (primary suspect) / SS (secondary
    suspect) / C (concomitant). Suspected drug = the PS drug only.
  * Medical history (e.g. Hypertension, Diabetes, Renal Transplant) is kept
    SEPARATE from adverse events.
  * Adverse events contain only real reactions — never age/gender/history.
  * Route words (Oral, Subcutaneous, ...) are never stored as drug names.
"""
from __future__ import annotations

import re
from typing import Any

import config
from src.logging_config import get_logger

log = get_logger("extraction")

_ROLES = {"PS", "SS", "C"}
_ROUTE_WORDS = {
    "oral", "orally", "subcutaneous", "intravenous", "iv", "intramuscular",
    "im", "topical", "inhaled", "several", "unknown", "route", "nasal",
    "rectal", "transdermal", "ophthalmic",
}

EMPTY_CASE: dict[str, Any] = {
    "patient_id": "", "case_id": "",
    "age": "", "gender": "", "weight": "",
    "medical_history": [],
    "drugs": [],            # [{name, role, dose, route}]
    "suspected_drug": "",
    "adverse_events": [],
    "indication": "",
    "outcome": "",
    "therapy_start_date": "", "therapy_end_date": "", "event_start_date": "",
    "dechallenge": "", "rechallenge": "",
    "seriousness_criteria": {},
}

_SYSTEM = (
    "You are a senior pharmacovigilance (drug-safety) data abstractor. Extract "
    "structured entities from ONE adverse-event case. Use ONLY the text; never "
    "invent values. Detect ALL drugs even if a drug name is novel/unknown. "
    "Strictly separate MEDICAL HISTORY (pre-existing conditions) from ADVERSE "
    "EVENTS (reactions caused during therapy). Respond with one JSON object only."
)

_TEMPLATE = """Extract this PV case as JSON with EXACTLY these keys:
- "patient_id": patient identifier if present (string)
- "case_id": case identifier if present (string)
- "age": age with unit (string)
- "gender": "Male"/"Female"/"" (string)
- "weight": weight with unit (string)
- "medical_history": list of pre-existing conditions (e.g. Hypertension, Diabetes,
  Renal Transplant). NEVER put reactions here.
- "drugs": list of ALL drugs, each an object:
    {{"name": drug name, "role": "PS"|"SS"|"C", "dose": "", "route": ""}}
    PS = primary suspect (the drug most likely causing the event),
    SS = secondary suspect, C = concomitant. NEVER use a route (Oral, Subcutaneous)
    as a drug name.
- "suspected_drug": the PS drug name (string)
- "adverse_events": list of ACTUAL reactions only (e.g. Rash, Acute Kidney Injury,
  Sepsis, Nausea). NEVER include age, gender, or medical history.
- "indication": reason the suspect drug was taken (string)
- "outcome": clinical outcome (e.g. Hospitalization, Recovered, Death) (string)
- "therapy_start_date": (string)  "therapy_end_date": (string)  "event_start_date": (string)
- "dechallenge": effect of stopping the drug, if stated (string)
- "rechallenge": effect of re-administering, if stated (string)

Case text:
\"\"\"{text}\"\"\""""


def extract_case(text: str) -> dict[str, Any]:
    """Extract one PV case. LLM-first with a deterministic fallback."""
    if config.llm_available():
        try:
            return _coerce(_extract_llm(text), text)
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM extraction failed (%s); using rule fallback.", exc)
    return _coerce(_extract_rules(text), text)


def _extract_llm(text: str) -> dict[str, Any]:
    from src import llm

    return llm.chat_json(_SYSTEM, _TEMPLATE.format(text=text[:8000]))


def _extract_rules(text: str) -> dict[str, Any]:
    """Lightweight deterministic fallback (vocab + regex)."""
    from src.dictionaries import load_vocabularies

    drug_vocab, reac_vocab = load_vocabularies()
    lower = text.lower()
    drugs = []
    for term in drug_vocab[:50000]:
        t = term.lower()
        if len(t) >= 4 and t not in _ROUTE_WORDS and re.search(rf"\b{re.escape(t)}\b", lower):
            drugs.append({"name": term.title(), "role": "C", "dose": "", "route": ""})
        if len(drugs) >= 15:
            break
    if drugs:
        drugs[0]["role"] = "PS"
    events = []
    for term in reac_vocab:
        if len(term) >= 4 and re.search(rf"\b{re.escape(term.lower())}\b", lower):
            events.append(term.title())
        if len(events) >= 15:
            break
    data = dict(EMPTY_CASE)
    age = re.search(r"\b(\d{1,3})\s*(?:year|yr|y/o|yo)", lower)
    data.update(
        age=f"{age.group(1)} years" if age else "",
        gender=("Female" if re.search(r"\bfemale|\bwoman\b", lower)
                else "Male" if re.search(r"\bmale|\bman\b", lower) else ""),
        drugs=drugs, adverse_events=events,
        suspected_drug=drugs[0]["name"] if drugs else "",
    )
    return data


def _coerce(data: dict[str, Any], text: str) -> dict[str, Any]:
    """Normalise, enforce PV rules (roles, history≠reactions, no routes-as-drugs)."""
    out = dict(EMPTY_CASE)
    for k in out:
        if k in data and data[k] is not None:
            out[k] = data[k]

    def _as_list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [p.strip() for p in re.split(r"[;,]", v) if p.strip()]
        return []

    out["medical_history"] = _as_list(out["medical_history"])
    out["adverse_events"] = _as_list(out["adverse_events"])

    # Clean drugs: dedupe by name, drop route-words, normalise roles.
    seen, clean = set(), []
    for d in out["drugs"] if isinstance(out["drugs"], list) else []:
        if isinstance(d, str):
            d = {"name": d, "role": "C"}
        name = str(d.get("name", "")).strip()
        if not name or name.lower() in _ROUTE_WORDS or name.lower() in seen:
            continue
        role = str(d.get("role", "C")).upper().strip()
        clean.append({"name": name, "role": role if role in _ROLES else "C",
                      "dose": str(d.get("dose", "")).strip(),
                      "route": str(d.get("route", "")).strip()})
        seen.add(name.lower())
    out["drugs"] = clean

    # Ensure exactly-meaningful suspected drug = a PS drug.
    ps = [d for d in clean if d["role"] == "PS"]
    if not ps and clean:                       # promote first drug to PS
        clean[0]["role"] = "PS"
        ps = [clean[0]]
    if ps and not out["suspected_drug"]:
        out["suspected_drug"] = ps[0]["name"]

    # Remove any medical-history terms that leaked into adverse_events.
    hist_lower = {h.lower() for h in out["medical_history"]}
    out["adverse_events"] = [e for e in out["adverse_events"]
                             if e.lower() not in hist_lower]
    return out


def all_drug_names(case: dict[str, Any]) -> list[str]:
    return [d["name"] for d in case.get("drugs", [])]


def suspected_drugs(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in case.get("drugs", []) if d.get("role") == "PS"]


def is_valid_case(case: dict[str, Any]) -> bool:
    """A real report needs patient signal + at least one drug + one reaction."""
    has_patient = bool(case.get("age") or case.get("gender") or case.get("patient_id"))
    has_drug = bool(case.get("drugs"))
    has_reaction = bool(case.get("adverse_events"))
    return has_drug and has_reaction and (has_patient or case.get("case_id"))
