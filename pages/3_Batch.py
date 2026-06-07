"""Batch page — analyze many cases at once (files and/or multiple narratives)."""
from __future__ import annotations

import streamlit as st

from src import batch as batch_mod
from src.settings_store import load_settings
from src.ui_theme import hero, inject_theme

st.set_page_config(page_title="PV Copilot · Batch", page_icon="🗃️", layout="wide")
inject_theme()
hero("Batch Analysis", "Upload several case documents or paste multiple narratives "
     "and process them all at once with concurrent batching.",
     pills=["Multi-file", "Concurrent", "Combined export"])

settings = load_settings()
st.caption(f"Backend `{settings['vector_backend']}` · model `{settings['embedding_model']}` "
           f"· engine `{settings['rag_engine']}` — change on the Settings page.")

col1, col2 = st.columns(2)
with col1:
    uploads = st.file_uploader(
        "Upload case documents (TXT / PDF / DOCX) — multiple allowed",
        type=["txt", "pdf", "docx"], accept_multiple_files=True)
with col2:
    multi_text = st.text_area(
        "...or paste multiple narratives (separate each case with a line of `---`)",
        height=180,
        placeholder="Case 1 narrative...\n---\nCase 2 narrative...\n---\nCase 3 narrative...")

report_date = st.text_input("Report Date", value="07-Jun-2026")

if st.button("🗃️ Run Batch Analysis", type="primary", use_container_width=True):
    items: list[batch_mod.BatchItem] = []
    for f in uploads or []:
        items.append(batch_mod.BatchItem(file_name=f.name, file_bytes=f.read()))
    for chunk in (multi_text or "").split("---"):
        if chunk.strip():
            items.append(batch_mod.BatchItem(text=chunk.strip()))

    if not items:
        st.warning("Add at least one file or one narrative.")
        st.stop()

    bar = st.progress(0.0, text=f"Analyzing 0/{len(items)} cases...")
    results = batch_mod.run_batch(
        items, settings=settings, report_date=report_date,
        progress=lambda d, t: bar.progress(d / t, text=f"Analyzing {d}/{t} cases..."))
    bar.empty()
    st.session_state["batch_results"] = results

results = st.session_state.get("batch_results")
if results:
    ok = sum(1 for r in results if r.get("ok"))
    serious = sum(1 for r in results if r.get("seriousness") == "Serious")
    c1, c2, c3 = st.columns(3)
    c1.metric("Cases processed", len(results))
    c2.metric("Succeeded", ok)
    c3.metric("Serious", serious)

    st.dataframe(
        [{"Case ID": r.get("case_id", ""), "Source": r.get("file_name") or "text",
          "Drug": r.get("drug", ""),
          "All Drugs": ", ".join(r.get("all_drugs", [])),
          "Adverse Events": ", ".join(r.get("events", [])),
          "Seriousness": r.get("seriousness", ""), "Causality": r.get("causality", ""),
          "Confidence": r.get("confidence", ""),
          "Status": "✅" if r.get("ok") else f"❌ {r.get('error', '')}"} for r in results],
        use_container_width=True, hide_index=True)

    st.markdown("### ⬇️ Download all reports")
    d1, d2 = st.columns(2)
    d1.download_button("🗜️ All PDFs (zip)", batch_mod.reports_zip(results),
                       file_name="batch_reports.zip", mime="application/zip",
                       use_container_width=True)
    d2.download_button("📊 Summary (Excel)", batch_mod.summary_excel(results),
                       file_name="batch_summary.xlsx", use_container_width=True,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
