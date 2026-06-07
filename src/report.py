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
            "Drug Name (Primary Suspect)": entities.get("drug") or "Unknown",
            "Other Reported Drugs": ", ".join(
                d for d in entities.get("all_drugs", [])
                if d and d != entities.get("drug")
            ) or "None reported",
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
            "Serious Adverse Drug Reaction (ADR) - Requires Medical Review"
            if analysis.get("seriousness") == "Serious"
            else "Non-Serious Adverse Event - Routine Monitoring"
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
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
        Table, TableStyle,
    )

    # --- palette ---
    NAVY = colors.HexColor("#10243e")
    BLUE = colors.HexColor("#1a4f7a")
    LIGHT = colors.HexColor("#eaf2f8")
    ZEBRA = colors.HexColor("#f6f9fc")
    BORDER = colors.HexColor("#cdd9e5")
    RED = colors.HexColor("#b3261e")
    GREEN = colors.HexColor("#1e7d3a")

    serious = report["case_information"].get("Seriousness") == "Serious"
    accent = RED if serious else GREEN

    styles = getSampleStyleSheet()
    title_st = ParagraphStyle("title", parent=styles["Title"], fontSize=18,
                              textColor=colors.white, spaceAfter=0, leading=22)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9,
                            textColor=colors.HexColor("#c6d6e6"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5,
                        textColor=BLUE, spaceBefore=12, spaceAfter=5, leading=14)
    key_st = ParagraphStyle("key", parent=styles["Normal"], fontSize=9,
                            fontName="Helvetica-Bold", textColor=NAVY, leading=12)
    val_st = ParagraphStyle("val", parent=styles["Normal"], fontSize=9,
                            textColor=colors.HexColor("#1f2d3d"), leading=12)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5,
                          leading=14, alignment=TA_LEFT, spaceAfter=2)
    badge_st = ParagraphStyle("badge", parent=styles["Normal"], fontSize=10,
                              fontName="Helvetica-Bold", textColor=colors.white,
                              alignment=1, leading=13)
    foot_st = ParagraphStyle("foot", parent=styles["Normal"], fontSize=7.5,
                             textColor=colors.HexColor("#8090a0"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=14 * mm, bottomMargin=16 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
        title="Pharmacovigilance AI Report",
        author="Pharmacovigilance AI Copilot",
    )
    avail_w = doc.width

    # --- header band ---
    ci = report["case_information"]
    header = Table(
        [[Paragraph("Adverse Event Case Report", title_st),
          Paragraph(report["case_information"].get("Seriousness", ""), badge_st)],
         [Paragraph("Pharmacovigilance AI Copilot &nbsp;&nbsp;|&nbsp;&nbsp; "
                    f"Case {_xml(ci.get('Case ID', ''))} &nbsp;&nbsp;|&nbsp;&nbsp; "
                    f"{_xml(ci.get('Report Date', ''))}", sub_st), ""]],
        colWidths=[avail_w - 38 * mm, 38 * mm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY),
        ("BACKGROUND", (1, 0), (1, 0), accent),
        ("BACKGROUND", (1, 1), (1, 1), NAVY),
        ("SPAN", (0, 0), (0, 0)), ("SPAN", (0, 1), (0, 1)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 10), ("RIGHTPADDING", (1, 0), (1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    def kv_table(section: dict[str, Any]) -> Table:
        rows = [[Paragraph(str(k), key_st), Paragraph(_cell(v), val_st)]
                for k, v in section.items()]
        table = Table(rows, colWidths=[48 * mm, avail_w - 48 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, ZEBRA]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
            ("LINEAFTER", (0, 0), (0, -1), 0.4, BORDER),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def section(title: str, key: str) -> KeepTogether:
        return KeepTogether([Paragraph(title, h2), kv_table(report[key])])

    flow: list[Any] = [
        header, Spacer(1, 10),
        section("Case Information", "case_information"),
        section("Patient Information", "patient_information"),
        section("Suspected Drug Information", "suspected_drug"),
        section("Adverse Event Details", "adverse_event"),
        section("Seriousness Assessment", "seriousness_assessment"),
        section("Causality Assessment (AI-Assisted)", "causality_assessment"),
        Paragraph("AI-Generated Narrative Summary", h2),
        Paragraph(_xml(report["ai_narrative_summary"]) or "—", body),
        Paragraph("AI Safety Insights", h2),
    ]
    for insight in report["ai_safety_insights"] or ["—"]:
        flow.append(Paragraph(f"•&nbsp; {_xml(insight)}", body))

    flow.append(Paragraph("Attachments / Source Documents", h2))
    for doc_name in report.get("source_documents") or ["—"]:
        flow.append(Paragraph(f"•&nbsp; {_xml(doc_name)}", body))

    # --- final classification banner ---
    final = Table([[Paragraph(_xml(report["final_classification"]), badge_st)]],
                  colWidths=[avail_w])
    final.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow += [Spacer(1, 12), final, Spacer(1, 8),
             HRFlowable(width="100%", thickness=0.5, color=BORDER),
             Paragraph(
                 f"Generated by {_xml(report.get('generated_by', 'PV AI Copilot'))} | "
                 "Decision-support only - not a substitute for qualified medical "
                 "review.", foot_st)]

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#8090a0"))
        canvas.drawRightString(doc_.pagesize[0] - 16 * mm, 9 * mm,
                               f"Page {doc_.page}")
        canvas.drawString(16 * mm, 9 * mm, str(ci.get("Case ID", "")))
        canvas.restoreState()

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _xml(text: Any) -> str:
    """Escape XML/markup-special chars so ReportLab Paragraph renders text safely."""
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _cell(value: Any) -> str:
    if isinstance(value, list):
        return _xml(", ".join(str(v) for v in value)) or "—"
    return _xml(value) if value not in (None, "") else "—"
