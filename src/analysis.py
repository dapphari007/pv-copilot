"""AI case analysis: narrative summary, seriousness, causality and insights.

Combines extracted entities + RAG context into a grounded LLM analysis, with a
fully deterministic fallback so the pipeline always returns a usable result.
"""
from __future__ import annotations

from typing import Any

import config
from src import llm, rag, seriousness

_ANALYSIS_SYSTEM = (
    "You are a senior pharmacovigilance assessor. Analyse the adverse-event case "
    "using ONLY the provided case text, extracted entities, and similar historical "
    "FAERS cases for context. Be precise, clinically cautious, and never fabricate "
    "patient data. Respond with a single JSON object and nothing else."
)

_ANALYSIS_TEMPLATE = """## Case narrative
{narrative}

## Extracted entities
{entities}

## Similar historical FAERS cases (retrieved context)
{context}

## Task
Produce a JSON object with EXACTLY these keys:
- "summary": a concise clinical narrative summary (3-5 sentences)
- "seriousness": "Serious" or "Non-Serious" per ICH E2A
- "seriousness_rationale": one sentence justifying the seriousness call
- "causality": one of "Certain", "Probable", "Possible", "Unlikely", "Unassessable"
- "confidence_score": float 0-1 reflecting confidence in the drug-event relationship
- "drug_event_relationship": short statement of the suspected drug-event link
- "medical_insights": list of 2-4 clinical observations (use historical context)
- "safety_observations": list of 1-3 safety/monitoring recommendations
"""


def analyze_case(
    narrative: str,
    entities: dict[str, Any],
    retrieved_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the full AI analysis, falling back to rules when the LLM is unavailable."""
    if retrieved_cases is None:
        retrieved_cases = rag.retrieve_similar_cases(narrative, entities)

    if config.llm_available():
        try:
            return _analyze_llm(narrative, entities, retrieved_cases)
        except Exception:
            pass
    return _analyze_rules(narrative, entities, retrieved_cases)


def _analyze_llm(narrative, entities, retrieved_cases) -> dict[str, Any]:
    context = rag.format_context(retrieved_cases)
    entity_lines = "\n".join(f"- {k}: {v}" for k, v in entities.items() if v)
    prompt = _ANALYSIS_TEMPLATE.format(
        narrative=narrative.strip(),
        entities=entity_lines or "None extracted.",
        context=context,
    )
    data = llm.chat_json(_ANALYSIS_SYSTEM, prompt)
    return _finalise(data, narrative, entities, retrieved_cases, source="llm")


def _analyze_rules(narrative, entities, retrieved_cases) -> dict[str, Any]:
    serious = seriousness.assess_from_text(narrative)
    events = ", ".join(entities.get("adverse_events", [])) or "the reported event(s)"
    drug = entities.get("drug") or "the suspected drug"
    age = entities.get("age", "")
    gender = (entities.get("gender") or "").lower()
    who = " ".join(p for p in [age, gender, "patient"] if p).strip() or "The patient"

    summary = (
        f"{who.capitalize()} experienced {events} following administration of {drug}. "
        f"Based on the documented outcome, the event is classified as "
        f"{serious['classification'].lower()}."
    )
    data = {
        "summary": summary,
        "seriousness": serious["classification"],
        "seriousness_rationale": (
            "Serious per ICH E2A outcome criteria."
            if serious["is_serious"]
            else "No serious-outcome criteria detected in the narrative."
        ),
        "causality": "Possible",
        "confidence_score": 0.5,
        "drug_event_relationship": f"Possible association between {drug} and {events}.",
        "medical_insights": [
            f"{len(retrieved_cases)} similar historical FAERS case(s) were retrieved for context."
        ]
        if retrieved_cases
        else ["No similar historical cases available for comparison."],
        "safety_observations": ["Further medical review recommended."],
    }
    return _finalise(data, narrative, entities, retrieved_cases, source="rules")


def finalize(data, narrative, entities, retrieved_cases, source) -> dict[str, Any]:
    """Public wrapper around :func:`_finalise` for alternative analysis engines."""
    return _finalise(data, narrative, entities, retrieved_cases, source)


# Prompt fragments reused by alternative engines (e.g. the LangChain path).
ANALYSIS_SYSTEM = _ANALYSIS_SYSTEM
ANALYSIS_TEMPLATE = _ANALYSIS_TEMPLATE


def _finalise(data, narrative, entities, retrieved_cases, source) -> dict[str, Any]:
    """Normalise types and cross-check seriousness against the rule engine."""
    rule_check = seriousness.assess_from_text(narrative)

    def _as_list(value):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    try:
        confidence = float(data.get("confidence_score", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return {
        "summary": str(data.get("summary", "")).strip(),
        "seriousness": data.get("seriousness") or rule_check["classification"],
        "seriousness_rationale": str(data.get("seriousness_rationale", "")).strip(),
        "causality": data.get("causality", "Possible"),
        "confidence_score": round(confidence, 2),
        "drug_event_relationship": str(data.get("drug_event_relationship", "")).strip(),
        "medical_insights": _as_list(data.get("medical_insights")),
        "safety_observations": _as_list(data.get("safety_observations")),
        "rule_based_seriousness": rule_check,
        "retrieved_case_count": len(retrieved_cases),
        "analysis_source": source,
    }
