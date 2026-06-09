"""Build the structured PV report dict from an extracted case + analysis.

Reuses the export functions in ``src/report.py`` (PDF/Excel/JSON) which are
extended to render the new "All Drugs" table and medical-history section.
"""
from __future__ import annotations

from typing import Any

from src import report as report_mod
from src.logging_config import get_logger

log = get_logger("report")

to_pdf = report_mod.to_pdf
to_excel = report_mod.to_excel
to_json = report_mod.to_json


def build_report(
    case: dict[str, Any],
    analysis: dict[str, Any],
    retrieved: list[dict[str, Any]] | None = None,
    *,
    case_id: str = "",
    report_date: str = "",
    source_documents: list[str] | None = None,
) -> dict[str, Any]:
    retrieved = retrieved or []
    ps = [d for d in case.get("drugs", []) if d.get("role") == "PS"]
    primary = ps[0] if ps else (case.get("drugs") or [{}])[0]
    serious = analysis.get("seriousness") == "Serious"
    criteria = analysis.get("seriousness_criteria", {})
    resolved_case_id = case_id or case.get("case_id") or "PV-CASE"

    return {
        "case_information": {
            "Case ID": resolved_case_id,
            "Patient ID": case.get("patient_id") or "—",
            "Report Type": "Spontaneous Report",
            "Report Date": report_date,
            "Seriousness": analysis.get("seriousness", ""),
            "Case Status": "Initial",
        },
        "patient_information": {
            "Age": case.get("age") or "Unknown",
            "Gender": case.get("gender") or "Unknown",
            "Weight": case.get("weight") or "Unknown",
        },
        "medical_history": case.get("medical_history", []) or ["None reported"],
        "suspected_drug": {
            "Drug Name": primary.get("name", "Unknown"),
            "Dose": primary.get("dose") or "Not reported",
            "Route": primary.get("route") or "Not reported",
            "Role": "Primary Suspect (PS)",
            "Indication": case.get("indication") or "Not reported",
        },
        "all_drugs": [
            {"Drug Name": d.get("name", ""), "Dose": d.get("dose", "") or "—",
             "Route": d.get("route", "") or "—",
             "Role": {"PS": "Primary Suspect", "SS": "Secondary Suspect",
                      "C": "Concomitant"}.get(d.get("role", "C"), d.get("role", ""))}
            for d in case.get("drugs", [])
        ],
        "adverse_event": {
            "Adverse Events": ", ".join(case.get("adverse_events", [])) or "Not reported",
            "Event Start Date": case.get("event_start_date") or "Not reported",
            "Outcome": case.get("outcome") or "Not reported",
            "Seriousness": analysis.get("seriousness", ""),
        },
        "ai_narrative_summary": analysis.get("narrative_summary", ""),
        "seriousness_assessment": {
            "Classification": analysis.get("seriousness", ""),
            "Death": _yn(criteria.get("Death")),
            "Life Threatening": _yn(criteria.get("Life Threatening")),
            "Hospitalization": _yn(criteria.get("Hospitalization")),
            "Disability": _yn(criteria.get("Disability")),
            "Congenital Anomaly": _yn(criteria.get("Congenital Anomaly")),
            "Medically Important": _yn(criteria.get("Medically Important Condition")),
            "Rationale": analysis.get("seriousness_rationale", ""),
        },
        "causality_assessment": {
            "Assessment": analysis.get("causality", ""),
            "Confidence Score": analysis.get("confidence_score", ""),
            "Justification": analysis.get("causality_justification", ""),
        },
        "ai_safety_insights": analysis.get("safety_insights", []),
        "similar_cases": [
            {"case_id": r.get("case_id", ""), "similarity": r.get("similarity", 0),
             "snippet": r.get("snippet", ""), "drug_match": r.get("drug_match", False),
             "reaction_match": r.get("reaction_match", [])}
            for r in retrieved
        ],
        "source_documents": source_documents
        or ["Patient narrative", "Physician notes", "Lab reports (if available)"],
        "final_classification": (
            "Serious Adverse Drug Reaction (ADR) - Requires Medical Review"
            if serious else "Non-Serious Adverse Event - Routine Monitoring"),
        "generated_by": "Pharmacovigilance AI Copilot",
    }


def _yn(value: Any) -> str:
    return "Yes" if value else "No"
