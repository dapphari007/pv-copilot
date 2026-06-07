"""Pharmacovigilance AI Copilot — Streamlit UI (Analyze home page).

Multipage app: this file is the Analyze page; see ``pages/`` for History and
Settings. Runtime configuration (vector backend, embedding model, RAG engine)
lives on the Settings page and is read from ``settings_store``.
"""
from __future__ import annotations

import io
import re

import streamlit as st

import config
from src import report as report_mod, storage, vectordb
from src.pipeline import run_analysis
from src.settings_store import load_settings
from src.ui_theme import inject_theme, hero

st.set_page_config(page_title="PV Copilot · Analyze", page_icon="💊", layout="wide")
inject_theme()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def read_upload(uploaded_file) -> tuple[str, bytes]:
    """Return (extracted_text, raw_bytes) for a TXT/PDF/DOCX upload."""
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages), data
        except Exception as exc:
            st.error(f"Could not read PDF: {exc}")
            return "", data
    if name.endswith(".docx"):
        try:
            import docx
            document = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs), data
        except Exception as exc:
            st.error(f"Could not read DOCX: {exc}")
            return "", data
    return data.decode("utf-8", errors="replace"), data


# --------------------------------------------------------------------------- #
# Sidebar — compact status (configuration lives on the Settings page)
# --------------------------------------------------------------------------- #
settings = load_settings()
with st.sidebar:
    st.markdown("### ⚙️ Active configuration")
    st.markdown(
        f"- **LLM:** {'Groq · ' + config.GROQ_MODEL if config.llm_available() else 'rule-based fallback'}\n"
        f"- **Vector DB:** `{settings['vector_backend']}`\n"
        f"- **Embedding:** `{settings['embedding_model']}`\n"
        f"- **RAG engine:** `{settings['rag_engine']}`\n"
        f"- **Top-K:** `{settings['top_k']}`"
    )
    if settings["embedding_model"] not in vectordb.available_models(settings["vector_backend"]):
        st.warning(
            f"No `{settings['embedding_model']}` index in `{settings['vector_backend']}`. "
            "Build it or switch on the **Settings** page."
        )
    st.caption("Change these on the **Settings** page →")
    st.divider()
    st.metric("Cases analyzed", storage.count_cases())
    st.caption("FDA FAERS 2026Q1 · decision-support only, not a medical device.")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
hero("Analyze an Adverse Event Case",
     "Extract safety entities, retrieve similar FAERS cases, and generate a "
     "structured PV report with AI seriousness & causality.")

with st.form("case_form"):
    col_text, col_meta = st.columns([3, 1])
    with col_text:
        narrative = st.text_area(
            "Adverse event narrative", height=180,
            placeholder="e.g. A 45-year-old female experienced severe skin rash and "
            "fever after taking Amoxicillin 500 mg orally for a bacterial infection. "
            "She was hospitalized and the drug was discontinued.",
        )
        uploaded = st.file_uploader(
            "...or upload a case document (TXT, PDF, DOCX) — stored locally",
            type=["txt", "pdf", "docx"],
        )
    with col_meta:
        case_id = st.text_input("Case ID", value="PV-2026-00125")
        report_date = st.text_input("Report Date", value="06-Jun-2026")
        st.caption("Results are saved to the local case history.")

    submitted = st.form_submit_button("🔬 Analyze Case", type="primary",
                                      use_container_width=True)

if submitted:
    text = narrative.strip()
    src_kind, fpath, fname, raw = "manual", None, None, None
    if uploaded is not None and not text:
        text, raw = read_upload(uploaded)
        text = text.strip()
        if text:
            st.info(f"Loaded {len(text):,} characters from **{uploaded.name}**.")
            src_kind, fname = "upload", uploaded.name

    if not text:
        st.warning("Please enter an adverse-event narrative or upload a document.")
        st.stop()

    if src_kind == "upload" and raw is not None:
        fpath = storage.save_upload(raw, fname)

    with st.status("Running pharmacovigilance pipeline...", expanded=True) as status:
        st.write("Extracting entities, retrieving FAERS cases, analyzing...")
        result = run_analysis(
            text, case_id=case_id, report_date=report_date, source=src_kind,
            file_path=fpath, file_name=fname,
            source_documents=[fname] if fname else ["Patient narrative (manual entry)"],
            settings=settings,
        )
        status.update(label="Analysis complete", state="complete", expanded=False)
    st.session_state["results"] = result


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
results = st.session_state.get("results")
if results:
    entities, analysis = results["entities"], results["analysis"]
    retrieved, report = results["retrieved"], results["report"]

    tab_e, tab_a, tab_c, tab_r = st.tabs(
        ["🧬 Entities", "🧠 AI Analysis", "📚 Similar Cases", "📄 Report & Downloads"])

    with tab_e:
        st.subheader("Extracted Safety Entities")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Suspect Drug", entities.get("drug") or "—")
        c2.metric("Age", entities.get("age") or "—")
        c3.metric("Gender", entities.get("gender") or "—")
        c4.metric("Weight", entities.get("weight") or "—")
        st.markdown("**All Reported Drugs**")
        st.write(", ".join(entities.get("all_drugs", [])) or entities.get("drug") or "—")
        st.markdown("**Adverse Events**")
        st.write(", ".join(entities.get("adverse_events", [])) or "—")
        st.json(entities, expanded=False)

    with tab_a:
        st.subheader("AI Case Analysis")
        is_serious = analysis.get("seriousness") == "Serious"
        c1, c2, c3 = st.columns(3)
        badge = "pv-serious" if is_serious else "pv-ok"
        c1.markdown(f"<div class='{badge}'>Seriousness: "
                    f"{analysis.get('seriousness', '—')}</div>", unsafe_allow_html=True)
        c2.info(f"Causality: {analysis.get('causality', '—')}")
        c3.metric("Confidence", f"{analysis.get('confidence_score', 0):.2f}")
        st.markdown("**Narrative Summary**")
        st.write(analysis.get("summary") or "—")
        st.caption(f"Rationale: {analysis.get('seriousness_rationale', '—')}")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Medical Insights**")
            for item in analysis.get("medical_insights", []) or ["—"]:
                st.markdown(f"- {item}")
        with col_b:
            st.markdown("**Safety Observations**")
            for item in analysis.get("safety_observations", []) or ["—"]:
                st.markdown(f"- {item}")
        st.caption(f"Engine: {analysis.get('analysis_source', '?')} · "
                   f"Retrieved: {analysis.get('retrieved_case_count', 0)} · "
                   f"Backend: {settings['vector_backend']} · Model: {settings['embedding_model']}")

    with tab_c:
        st.subheader(f"Similar Historical FAERS Cases ({len(retrieved)})")
        if not retrieved:
            st.info("No retrieval results — check the index on the Settings page.")
        for i, case in enumerate(retrieved, start=1):
            with st.expander(f"Case {i} — id {case.get('primaryid', '?')} "
                             f"(similarity {case.get('similarity', 0):.2f})"):
                st.write(case.get("narrative", ""))

    with tab_r:
        st.subheader("Structured Pharmacovigilance Report")
        st.success(report["final_classification"])
        cols = st.columns(2)
        for i, (title, key) in enumerate([
            ("Case Information", "case_information"),
            ("Patient Information", "patient_information"),
            ("Suspected Drug", "suspected_drug"),
            ("Adverse Event", "adverse_event"),
        ]):
            with cols[i % 2]:
                st.markdown(f"**{title}**")
                st.table({"Field": list(report[key].keys()),
                          "Value": [report_mod._cell(v) for v in report[key].values()]})
        st.markdown("**AI Narrative Summary**")
        st.write(report["ai_narrative_summary"])

        st.divider()
        st.markdown("### ⬇️ Download Report")
        raw_id = report["case_information"].get("Case ID") or "PV-report"
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw_id)).strip("_") or "PV-report"
        d1, d2, d3 = st.columns(3)
        d1.download_button("📄 PDF", report_mod.to_pdf(report),
                           file_name=f"{safe_id}.pdf", mime="application/pdf",
                           use_container_width=True)
        d2.download_button("📊 Excel", report_mod.to_excel(report),
                           file_name=f"{safe_id}.xlsx", use_container_width=True,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        d3.download_button("🧾 JSON", report_mod.to_json(report),
                           file_name=f"{safe_id}.json", mime="application/json",
                           use_container_width=True)
