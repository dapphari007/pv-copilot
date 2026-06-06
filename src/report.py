"""Structured Pharmacovigilance report assembly and export (JSON / Excel / PDF).

The report schema mirrors the project's sample PV report: case info, patient,
suspect drug, adverse-event details, AI narrative, seriousness, causality, key
entities and safety insights.
"""
from __future__ import annotations

import io
import json
from typing import Any


def build_report(
    entities: dict[str, Any],
    analysis: dict[str, Any],
    *,
    case_id: str = "PV-DRAFT-0001",
    report_date: str = "",
    retrieved_cases: list[dict[str, Any]] | None = None,
    source_documents: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the canonical report dictionary from entities + analysis."""
    serious = analysis.get("rule_based_seriousness", {})
    criteria = serious.get("criteria", {})
    return {
        "case_information": {
            "Case ID": case_id,
            "Report Type": "Spontaneous Report",
            "Report Date": report_date,
            "Seriousness": analysis.get("seriousness", ""),
            "Case Status": "Initial",
        },
        "patient_information": {
            "Age": entities.get("age") or "Unknown",
            "Gender": entities.get("gender") or "Unknown",
            "Weight": entities.get("weight") or "Unknown",
            "Medical History": entities.get("medical_history") or "Not reported",
        },
        "suspected_drug": {
            "Drug Name": entities.get("drug") or "Unknown",
            "Dosage": entities.get("dosage") or "Not reported",
            "Route": entities.get("route") or "Not reported",
            "Therapy Start Date": entities.get("therapy_start_date") or "Not reported",
            "Therapy End Date": entities.get("therapy_end_date") or "Not reported",
            "Indication": entities.get("indication") or "Not reported",
        },
        "adverse_event": {
            "Adverse Event": ", ".join(entities.get("adverse_events", [])) or "Not reported",
            "Event Start Date": entities.get("event_start_date") or "Not reported",
            "Outcome": entities.get("outcome") or "Not reported",
            "Severity": entities.get("severity") or "Not reported",
            "Action Taken": entities.get("action_taken") or "Not reported",
            "Seriousness": analysis.get("seriousness", ""),
        },
        "ai_narrative_summary": analysis.get("summary", ""),
        "seriousness_assessment": {
            "Hospitalization": _yn(criteria.get("Hospitalization")),
            "Life Threatening": _yn(criteria.get("Life Threatening")),
            "Disability": _yn(criteria.get("Disability")),
            "Death": _yn(criteria.get("Death")),
            "Rationale": analysis.get("seriousness_rationale", ""),
        },
        "causality_assessment": {
            "Suspected Relationship": analysis.get("causality", ""),
            "Confidence Score": analysis.get("confidence_score", ""),
            "Drug-Event Relationship": analysis.get("drug_event_relationship", ""),
        },
        "key_entities": {
            "Drug": entities.get("drug", ""),
            "All Drugs": entities.get("all_drugs", []),
            "Adverse Events": entities.get("adverse_events", []),
            "Outcome": entities.get("outcome", ""),
        },
        "ai_safety_insights": analysis.get("medical_insights", [])
        + analysis.get("safety_observations", []),
        "source_documents": source_documents
        or ["Patient narrative", "Physician notes", "Lab reports (if available)"],
        "similar_cases": [
            {
                "primaryid": c.get("primaryid", ""),
                "similarity": round(float(c.get("similarity", 0.0)), 3),
                "narrative": c.get("narrative", ""),
            }
            for c in (retrieved_cases or [])
        ],
        "final_classification": (
            "Serious Adverse Drug Reaction (ADR) — Requires Medical Review"
            if analysis.get("seriousness") == "Serious"
            else "Non-Serious Adverse Event — Routine Monitoring"
        ),
        "generated_by": "Pharmacovigilance AI Copilot",
    }


def _yn(value: Any) -> str:
    return "Yes" if value else "No"


# --------------------------------------------------------------------------- #
# Exporters
# --------------------------------------------------------------------------- #
def to_json(report: dict[str, Any]) -> bytes:
    return json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")


def to_excel(report: dict[str, Any]) -> bytes:
    import pandas as pd

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for section in (
            "case_information", "patient_information", "suspected_drug",
            "adverse_event", "seriousness_assessment", "causality_assessment",
        ):
            df = pd.DataFrame(
                list(report[section].items()), columns=["Field", "Value"]
            )
            df.to_excel(writer, sheet_name=_sheet(section), index=False)

        pd.DataFrame({"AI Narrative Summary": [report["ai_narrative_summary"]]}).to_excel(
            writer, sheet_name="Narrative", index=False
        )
        pd.DataFrame({"Safety Insights": report["ai_safety_insights"] or [""]}).to_excel(
            writer, sheet_name="Safety Insights", index=False
        )
        pd.DataFrame({"Source Documents": report.get("source_documents") or [""]}).to_excel(
            writer, sheet_name="Source Documents", index=False
        )
        if report["similar_cases"]:
            pd.DataFrame(report["similar_cases"]).to_excel(
                writer, sheet_name="Similar Cases", index=False
            )
    return buffer.getvalue()


def _sheet(name: str) -> str:
    return name.replace("_", " ").title()[:31]


def to_pdf(report: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title="Pharmacovigilance AI Report",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=12,
        textColor=colors.HexColor("#1a4f7a"), spaceBefore=10, spaceAfter=4,
    )
    body = styles["BodyText"]

    flow: list[Any] = [
        Paragraph("Adverse Event Case Report", h1),
        Paragraph("Pharmacovigilance AI Copilot", styles["Italic"]),
        Spacer(1, 8),
    ]

    def kv_table(section: dict[str, Any]) -> Table:
        rows = [[str(k), _cell(v)] for k, v in section.items()]
        table = Table(rows, colWidths=[55 * mm, 110 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf2f8")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0c4d4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#f7fafc")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table

    sections = [
        ("Case Information", "case_information"),
        ("Patient Information", "patient_information"),
        ("Suspected Drug Information", "suspected_drug"),
        ("Adverse Event Details", "adverse_event"),
        ("Seriousness Assessment", "seriousness_assessment"),
        ("Causality Assessment (AI-Assisted)", "causality_assessment"),
    ]
    for title, key in sections:
        flow.append(Paragraph(title, h2))
        flow.append(kv_table(report[key]))

    flow.append(Paragraph("AI-Generated Narrative Summary", h2))
    flow.append(Paragraph(report["ai_narrative_summary"] or "—", body))

    flow.append(Paragraph("AI Safety Insights", h2))
    for insight in report["ai_safety_insights"] or ["—"]:
        flow.append(Paragraph(f"• {insight}", body))

    flow.append(Paragraph("Attachments / Source Documents", h2))
    for doc_name in report.get("source_documents") or ["—"]:
        flow.append(Paragraph(f"• {doc_name}", body))

    flow.append(Paragraph("Final Case Classification", h2))
    flow.append(Paragraph(report["final_classification"], body))

    doc.build(flow)
    return buffer.getvalue()


def _cell(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    return str(value) if value not in (None, "") else "—"
