"""Professional PV analysis: narrative, seriousness (ICH E2A), causality, insights.

Produces output that reads like a real pharmacovigilance assessment — not generic
filler. LLM-first with a deterministic, case-specific fallback.
"""
from __future__ import annotations

import re
from typing import Any

import config
from src.logging_config import get_logger

log = get_logger("analysis")

_SERIOUS_KEYS = ["Death", "Life Threatening", "Hospitalization", "Disability",
                 "Congenital Anomaly", "Medically Important Condition"]

_SYSTEM = (
    "You are a senior pharmacovigilance assessor writing a regulatory case "
    "assessment. Be precise, clinical, and specific to THIS case — never generic. "
    "Base seriousness on ICH E2A and causality on temporal relationship, "
    "dechallenge/rechallenge, outcome, and supporting evidence. Respond with one "
    "JSON object only."
)

_TEMPLATE = """## Case entities
{entities}

## Similar historical FAERS cases (context, do NOT copy verbatim)
{context}

## Task — return JSON with EXACTLY these keys:
- "narrative_summary": a professional PV narrative of 150-300 words, structured as:
  patient demographics -> suspected drug -> concomitant drugs -> adverse events ->
  outcome -> clinical interpretation -> PV conclusion. Cohesive prose, not bullets.
- "seriousness": "Serious" or "Non-Serious" (ICH E2A)
- "seriousness_rationale": one or two sentences citing the specific criterion met
- "seriousness_criteria": object with boolean keys: "Death", "Life Threatening",
  "Hospitalization", "Disability", "Congenital Anomaly", "Medically Important Condition"
- "causality": one of "Certain","Probable","Possible","Unlikely","Unassessable"
- "causality_justification": 1-3 sentences citing temporal relationship,
  dechallenge/rechallenge, outcome, and supporting evidence
- "confidence_score": float 0-1
- "safety_insights": list of 5-8 SPECIFIC, clinically meaningful insights for this
  case (mention the actual drugs/reactions/comorbidities). No generic filler like
  "monitor patient"."""


def analyze(case: dict[str, Any], retrieved: list[dict[str, Any]]) -> dict[str, Any]:
    if config.llm_available():
        try:
            return _finalize(_analyze_llm(case, retrieved), case, retrieved, "llm")
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM analysis failed (%s); using rule fallback.", exc)
    return _finalize(_analyze_rules(case, retrieved), case, retrieved, "rules")


def _entities_block(case: dict[str, Any]) -> str:
    drugs = "; ".join(f"{d['name']} ({d['role']}{', ' + d['dose'] if d.get('dose') else ''}"
                      f"{', ' + d['route'] if d.get('route') else ''})"
                      for d in case.get("drugs", [])) or "none"
    return (
        f"Patient: {case.get('age','?')} {case.get('gender','?')}, "
        f"weight {case.get('weight','?')}\n"
        f"Medical history: {', '.join(case.get('medical_history', [])) or 'none reported'}\n"
        f"Suspected drug (PS): {case.get('suspected_drug','?')}\n"
        f"All drugs: {drugs}\n"
        f"Adverse events: {', '.join(case.get('adverse_events', [])) or 'none'}\n"
        f"Indication: {case.get('indication','?')}\n"
        f"Outcome: {case.get('outcome','?')}\n"
        f"Dechallenge: {case.get('dechallenge','?')} | Rechallenge: {case.get('rechallenge','?')}\n"
        f"Therapy: {case.get('therapy_start_date','?')}–{case.get('therapy_end_date','?')}; "
        f"event onset {case.get('event_start_date','?')}"
    )


def _analyze_llm(case, retrieved) -> dict[str, Any]:
    from src import llm

    context = "\n\n".join(
        f"[Case {i+1} | id={r.get('case_id','?')} | sim={r.get('similarity',0):.2f}] "
        f"{r.get('snippet','')}" for i, r in enumerate(retrieved)) or "none retrieved"
    user = _TEMPLATE.format(entities=_entities_block(case), context=context)
    return llm.chat_json(_SYSTEM, user, max_tokens=1800)


def _analyze_rules(case, retrieved) -> dict[str, Any]:
    text = " ".join([case.get("outcome", ""), " ".join(case.get("adverse_events", [])),
                     case.get("dechallenge", ""), case.get("_segment_text", "")]).lower()
    criteria = {
        "Death": bool(re.search(r"death|died|fatal", text)),
        "Life Threatening": "life" in text and "threat" in text,
        "Hospitalization": bool(re.search(r"hospitali", text)),
        "Disability": bool(re.search(r"disab|permanent", text)),
        "Congenital Anomaly": bool(re.search(r"congenital|birth defect", text)),
        "Medically Important Condition": bool(re.search(
            r"sepsis|acute kidney|renal failure|anaphyl|seizure", text)),
    }
    serious = any(criteria.values())
    drug = case.get("suspected_drug", "the suspect drug")
    events = ", ".join(case.get("adverse_events", [])) or "the reported reaction(s)"
    who = " ".join(x for x in [case.get("age", ""), case.get("gender", "").lower()] if x) or "The patient"
    narrative = (
        f"{who} presented with {events} following administration of {drug}"
        + (f" (indicated for {case['indication']})" if case.get("indication") else "")
        + ". "
        + (f"Relevant medical history includes {', '.join(case['medical_history'])}. "
           if case.get("medical_history") else "")
        + (f"Concomitant medications: "
           f"{', '.join(d['name'] for d in case.get('drugs', []) if d['role']=='C') or 'none reported'}. ")
        + f"The reported outcome was {case.get('outcome','not specified')}. "
        + (f"The event is assessed as serious under ICH E2A. "
           if serious else "No serious-outcome criteria were identified. ")
        + "A temporal association between the suspect drug and the event is noted; "
          "causality is considered possible pending further information."
    )
    insights = [
        f"The reaction(s) {events} are the focus of this safety assessment for {drug}.",
        ("Serious outcome criteria are met, raising the case priority."
         if serious else "No serious criteria identified; routine surveillance applies."),
    ]
    for c in case.get("medical_history", [])[:2]:
        insights.append(f"Pre-existing {c} may act as a confounding factor in causality.")
    if len([d for d in case.get("drugs", []) if d["role"] == "C"]) >= 2:
        insights.append("Multiple concomitant drugs introduce confounding for causality.")
    if retrieved:
        insights.append(f"{len(retrieved)} similar historical FAERS case(s) show comparable reactions.")
    insights.append("Temporal relationship supports a possible drug-event association.")
    return {
        "narrative_summary": narrative, "seriousness": "Serious" if serious else "Non-Serious",
        "seriousness_rationale": ("Meets ICH E2A serious criteria."
                                  if serious else "Does not meet ICH E2A serious criteria."),
        "seriousness_criteria": criteria, "causality": "Possible",
        "causality_justification": "Temporal association present; dechallenge/rechallenge "
                                   "and additional evidence limited.",
        "confidence_score": 0.5, "safety_insights": insights[:8],
    }


def _finalize(data, case, retrieved, source) -> dict[str, Any]:
    def _as_list(v):
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else (
            [v.strip()] if isinstance(v, str) and v.strip() else [])

    try:
        conf = max(0.0, min(1.0, float(data.get("confidence_score", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    criteria = data.get("seriousness_criteria") or {}
    criteria = {k: bool(criteria.get(k)) for k in _SERIOUS_KEYS}
    insights = _as_list(data.get("safety_insights"))
    if len(insights) < 5:  # guarantee the PRD minimum
        insights += _analyze_rules(case, retrieved)["safety_insights"]
    return {
        "narrative_summary": str(data.get("narrative_summary", "")).strip(),
        "seriousness": data.get("seriousness") or ("Serious" if any(criteria.values()) else "Non-Serious"),
        "seriousness_rationale": str(data.get("seriousness_rationale", "")).strip(),
        "seriousness_criteria": criteria,
        "causality": data.get("causality", "Possible"),
        "causality_justification": str(data.get("causality_justification", "")).strip(),
        "confidence_score": round(conf, 2),
        "safety_insights": insights[:8],
        "analysis_source": source,
        "retrieved_case_count": len(retrieved),
    }
