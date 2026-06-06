"""Pharmacovigilance AI Copilot — Streamlit application.

End-to-end flow: input/upload -> entity extraction -> RAG retrieval over FAERS
-> AI analysis (summary / seriousness / causality) -> structured report with
PDF / Excel / JSON downloads.
"""
from __future__ import annotations

import io
import re

import streamlit as st

import config
from src import analysis as analysis_mod
from src import extraction, rag, rag_langchain, report as report_mod
from src import vector_store

st.set_page_config(
    page_title="Pharmacovigilance AI Copilot",
    page_icon="💊",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; max-width: 1200px; }
      /* Hero banner */
      .pv-hero {
        background: linear-gradient(120deg, #10243e 0%, #1a4f7a 60%, #2a72a8 100%);
        border-radius: 14px; padding: 1.3rem 1.6rem; margin-bottom: 1.2rem;
        color: #fff; box-shadow: 0 6px 22px rgba(16,36,62,.25);
      }
      .pv-hero h1 { color:#fff; font-size:1.7rem; margin:0; font-weight:700; }
      .pv-hero p { color:#cfe0f0; margin:.35rem 0 0; font-size:.92rem; }
      .pv-pill { display:inline-block; background:rgba(255,255,255,.16);
        border:1px solid rgba(255,255,255,.25); border-radius:999px;
        padding:.12rem .7rem; font-size:.72rem; margin-right:.4rem; color:#eaf2f8; }
      /* Metric cards */
      div[data-testid="stMetric"] { background:#f6f9fc; border:1px solid #e2e9f0;
        border-radius:10px; padding:.7rem .9rem; }
      /* Tabs */
      button[data-baseweb="tab"] { font-weight:600; }
      /* Buttons */
      .stDownloadButton button, div[data-testid="stFormSubmitButton"] button {
        border-radius:9px; font-weight:600; }
      /* Section badges */
      .pv-serious { background:#fdecea; color:#b3261e; border:1px solid #f3b4ad;
        padding:.45rem .8rem; border-radius:9px; font-weight:700; }
      .pv-ok { background:#e8f5ec; color:#1e7d3a; border:1px solid #aedcbb;
        padding:.45rem .8rem; border-radius:9px; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def read_upload(uploaded_file) -> str:
    """Extract text from an uploaded TXT, PDF, or DOCX file."""
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # pragma: no cover - surfaced in UI
            st.error(f"Could not read PDF: {exc}")
            return ""
    if name.endswith(".docx"):
        try:
            import docx

            document = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs)
        except Exception as exc:  # pragma: no cover
            st.error(f"Could not read DOCX: {exc}")
            return ""
    return data.decode("utf-8", errors="replace")


def available_model_keys() -> list[str]:
    return vector_store.available_models()


def run_pipeline(
    narrative: str, case_id: str, report_date: str,
    source_documents: list[str] | None = None,
    model_key: str = "minilm",
    engine: str = "Native",
) -> dict:
    """Execute extraction -> retrieval -> analysis -> report and return results."""
    with st.status("Running pharmacovigilance pipeline...", expanded=True) as status:
        st.write("Extracting safety entities...")
        entities = extraction.extract_entities(narrative)

        if engine == "LangChain" and rag_langchain.langchain_available():
            st.write(f"Retrieving + analyzing via LangChain ({model_key})...")
            lc = rag_langchain.analyze_case_langchain(narrative, entities, model_key)
            retrieved, analysis = lc["retrieved"], lc["analysis"]
        else:
            st.write(f"Retrieving similar FAERS cases ({model_key})...")
            retrieved = rag.retrieve_similar_cases(narrative, entities, model_key=model_key)
            st.write("Generating AI case analysis...")
            analysis = analysis_mod.analyze_case(narrative, entities, retrieved)

        st.write("Assembling structured PV report...")
        report = report_mod.build_report(
            entities, analysis,
            case_id=case_id, report_date=report_date, retrieved_cases=retrieved,
            source_documents=source_documents,
        )
        status.update(label="Analysis complete", state="complete", expanded=False)

    return {
        "entities": entities,
        "retrieved": retrieved,
        "analysis": analysis,
        "report": report,
    }


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ System Status")

    if config.llm_available():
        st.success(f"LLM: Groq ({config.GROQ_MODEL})")
    else:
        st.warning("LLM: rule-based fallback\n(set GROQ_API_KEY for AI analysis)")

    st.subheader("🧬 Embedding model")
    built = available_model_keys()
    if built:
        selected_model = st.selectbox(
            "Vector index used for retrieval",
            options=built,
            format_func=lambda k: config.EMBEDDING_MODELS[k]["label"],
            help="The model that built an index must also query it; switching "
                 "models searches a different index.",
        )
        n_vectors = vector_store.load_index(selected_model).ntotal
        st.caption(f"✅ {n_vectors:,} FAERS cases indexed")
    else:
        selected_model = config.DEFAULT_MODEL_KEY
        st.error("No RAG index built. Run `python scripts/build_index.py`.")

    # Show which registry models are still pending a build.
    pending = [k for k in config.EMBEDDING_MODELS if k not in built]
    if pending:
        st.caption(
            "⏳ Not yet built: "
            + ", ".join(config.EMBEDDING_MODELS[k]["label"] for k in pending)
        )

    st.subheader("🔗 RAG engine")
    engine_options = ["Native"]
    if rag_langchain.langchain_available():
        engine_options.append("LangChain")
    selected_engine = st.radio(
        "Orchestration",
        options=engine_options,
        horizontal=True,
        help="Native = lightweight pipeline. LangChain = LCEL chain "
             "(ChatGroq + custom FAISS retriever).",
    )
    if "LangChain" not in engine_options:
        st.caption("LangChain path needs `langchain-groq` + a Groq key.")

    st.divider()
    st.caption(
        "Data source: FDA FAERS 2026Q1. This tool supports case triage and is "
        "**not** a substitute for qualified medical review."
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="pv-hero">
      <h1>💊 Pharmacovigilance AI Copilot</h1>
      <p>Extract safety entities · retrieve similar FAERS cases · generate a
         structured adverse-event report with AI seriousness &amp; causality.</p>
      <div style="margin-top:.7rem">
        <span class="pv-pill">FDA FAERS 2026Q1</span>
        <span class="pv-pill">RAG over 397K cases</span>
        <span class="pv-pill">Groq LLM</span>
        <span class="pv-pill">ICH E2A seriousness</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.form("case_form"):
    col_text, col_meta = st.columns([3, 1])
    with col_text:
        narrative = st.text_area(
            "Adverse event narrative",
            height=180,
            placeholder="e.g. A 45-year-old female experienced severe skin rash and "
            "fever after taking Amoxicillin 500 mg orally for a bacterial infection. "
            "She was hospitalized and the drug was discontinued.",
        )
        uploaded = st.file_uploader(
            "...or upload a case document (TXT, PDF, DOCX)",
            type=["txt", "pdf", "docx"],
        )
    with col_meta:
        case_id = st.text_input("Case ID", value="PV-2026-00125")
        report_date = st.text_input("Report Date", value="06-Jun-2026")

    submitted = st.form_submit_button("🔬 Analyze Case", type="primary")

if submitted:
    text = narrative.strip()
    source_documents = ["Patient narrative (manual entry)"]
    if uploaded is not None and not text:
        text = read_upload(uploaded).strip()
        if text:
            st.info(f"Loaded {len(text):,} characters from **{uploaded.name}**.")
            source_documents = [uploaded.name]

    if not text:
        st.warning("Please enter an adverse-event narrative or upload a document.")
        st.stop()

    st.session_state["results"] = run_pipeline(
        text, case_id, report_date, source_documents=source_documents,
        model_key=selected_model, engine=selected_engine,
    )
    st.session_state["narrative"] = text


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
results = st.session_state.get("results")
if results:
    entities = results["entities"]
    analysis = results["analysis"]
    retrieved = results["retrieved"]
    report = results["report"]

    tab_entities, tab_analysis, tab_cases, tab_report = st.tabs(
        ["🧬 Entities", "🧠 AI Analysis", "📚 Similar Cases", "📄 Report & Downloads"]
    )

    with tab_entities:
        st.subheader("Extracted Safety Entities")
        c1, c2, c3 = st.columns(3)
        c1.metric("Suspect Drug", entities.get("drug") or "—")
        c2.metric("Age", entities.get("age") or "—")
        c3.metric("Gender", entities.get("gender") or "—")

        c4, c5 = st.columns(2)
        with c4:
            st.markdown("**Adverse Events**")
            events = entities.get("adverse_events", [])
            st.write(", ".join(events) if events else "—")
            st.markdown("**All Drugs**")
            drugs = entities.get("all_drugs", [])
            st.write(", ".join(drugs) if drugs else "—")
        with c5:
            st.markdown("**Dosage / Route**")
            st.write(f"{entities.get('dosage') or '—'} · {entities.get('route') or '—'}")
            st.markdown("**Indication**")
            st.write(entities.get("indication") or "—")
        st.json(entities, expanded=False)

    with tab_analysis:
        st.subheader("AI Case Analysis")
        is_serious = analysis.get("seriousness") == "Serious"
        c1, c2, c3 = st.columns(3)
        (c1.error if is_serious else c1.success)(
            f"Seriousness: {analysis.get('seriousness', '—')}"
        )
        c2.info(f"Causality: {analysis.get('causality', '—')}")
        c3.metric("Confidence", f"{analysis.get('confidence_score', 0):.2f}")

        st.markdown("**Narrative Summary**")
        st.write(analysis.get("summary") or "—")
        st.caption(f"Seriousness rationale: {analysis.get('seriousness_rationale', '—')}")

        st.markdown("**Drug–Event Relationship**")
        st.write(analysis.get("drug_event_relationship") or "—")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Medical Insights**")
            for item in analysis.get("medical_insights", []) or ["—"]:
                st.markdown(f"- {item}")
        with col_b:
            st.markdown("**Safety Observations**")
            for item in analysis.get("safety_observations", []) or ["—"]:
                st.markdown(f"- {item}")

        st.caption(
            f"Analysis engine: {analysis.get('analysis_source', '?')} · "
            f"Retrieved cases: {analysis.get('retrieved_case_count', 0)}"
        )

    with tab_cases:
        st.subheader(f"Similar Historical FAERS Cases ({len(retrieved)})")
        if not retrieved:
            st.info(
                "No retrieval results. Build the index with "
                "`python scripts/build_index.py` to enable RAG."
            )
        for i, case in enumerate(retrieved, start=1):
            with st.expander(
                f"Case {i} — id {case.get('primaryid', '?')} "
                f"(similarity {case.get('similarity', 0):.2f}) · "
                f"{case.get('seriousness', '')}"
            ):
                st.write(case.get("narrative", ""))

    with tab_report:
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
                st.table(
                    {"Field": list(report[key].keys()),
                     "Value": [report_mod._cell(v) for v in report[key].values()]}
                )

        st.markdown("**AI Narrative Summary**")
        st.write(report["ai_narrative_summary"])

        st.markdown("**Attachments / Source Documents**")
        for doc_name in report.get("source_documents", []):
            st.markdown(f"- {doc_name}")

        st.divider()
        st.markdown("### ⬇️ Download Report")
        raw_id = report["case_information"].get("Case ID") or "PV-report"
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw_id)).strip("_") or "PV-report"
        d1, d2, d3 = st.columns(3)
        d1.download_button(
            "📄 PDF", report_mod.to_pdf(report),
            file_name=f"{safe_id}.pdf",
            mime="application/pdf", use_container_width=True,
        )
        d2.download_button(
            "📊 Excel", report_mod.to_excel(report),
            file_name=f"{safe_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        d3.download_button(
            "🧾 JSON", report_mod.to_json(report),
            file_name=f"{safe_id}.json",
            mime="application/json", use_container_width=True,
        )
