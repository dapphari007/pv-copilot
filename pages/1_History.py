"""History page — browse previously analyzed cases stored in SQLite."""
from __future__ import annotations

import re

import streamlit as st

from src import report as report_mod, storage
from src.ui_theme import hero, inject_theme

st.set_page_config(page_title="PV Copilot · History", page_icon="📜", layout="wide")
inject_theme()
hero("Case History", "Every analyzed case is stored locally (SQLite). Browse, "
                     "review, and re-download past reports.", pills=["Local SQLite store"])

cases = storage.list_cases(limit=200)
if not cases:
    st.info("No cases yet. Analyze one on the **Analyze** page to populate history.")
    st.stop()

st.caption(f"{len(cases)} case(s) stored · newest first")
st.dataframe(
    [{"When": c["created_at"], "Case ID": c["case_id"], "Drug": c["drug"],
      "Seriousness": c["seriousness"], "Causality": c["causality"],
      "Source": c["source"], "Model": c["embedding_model"],
      "Backend": c["vector_backend"]} for c in cases],
    use_container_width=True, hide_index=True,
)

st.divider()
label_for = {f"{c['created_at']} · {c['case_id'] or c['id'][:8]} · "
             f"{c['drug'] or '—'} ({c['seriousness'] or '—'})": c["id"] for c in cases}
choice = st.selectbox("Open a case", options=list(label_for))
row_id = label_for[choice]
record = storage.get_case(row_id)

if record:
    analysis, report = record["analysis"], record["report"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Seriousness", analysis.get("seriousness", "—"))
    c2.metric("Causality", analysis.get("causality", "—"))
    c3.metric("Confidence", f"{analysis.get('confidence_score', 0):.2f}")

    if record.get("file_name"):
        st.caption(f"📎 Source file: `{record['file_name']}` "
                   f"(stored at `{record.get('file_path', '')}`)")

    st.markdown("**Original prompt / narrative**")
    st.write(record["prompt"])
    st.markdown("**AI Narrative Summary**")
    st.write(report.get("ai_narrative_summary", "—"))

    with st.expander("Full report (JSON)"):
        st.json(report)

    raw_id = report.get("case_information", {}).get("Case ID") or "PV-report"
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw_id)).strip("_") or "PV-report"
    d1, d2, d3 = st.columns(3)
    d1.download_button("📄 PDF", report_mod.to_pdf(report), file_name=f"{safe_id}.pdf",
                       mime="application/pdf", use_container_width=True)
    d2.download_button("📊 Excel", report_mod.to_excel(report), file_name=f"{safe_id}.xlsx",
                       use_container_width=True,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d3.download_button("🧾 JSON", report_mod.to_json(report), file_name=f"{safe_id}.json",
                       mime="application/json", use_container_width=True)
