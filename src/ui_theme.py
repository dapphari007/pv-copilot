"""Shared Streamlit theme: injected CSS + reusable hero banner.

Imported by every page so the multipage app has a consistent, modern look.
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
  .block-container { padding-top: 2.0rem; max-width: 1200px; }
  #MainMenu, footer { visibility: hidden; }
  .pv-hero {
    background: linear-gradient(120deg, #0d1f36 0%, #1a4f7a 58%, #2a82b8 100%);
    border-radius: 16px; padding: 1.35rem 1.7rem; margin-bottom: 1.3rem;
    color: #fff; box-shadow: 0 8px 26px rgba(13,31,54,.28);
  }
  .pv-hero h1 { color:#fff; font-size:1.65rem; margin:0; font-weight:750; letter-spacing:.2px; }
  .pv-hero p { color:#d4e4f3; margin:.4rem 0 0; font-size:.93rem; max-width:760px; }
  .pv-pill { display:inline-block; background:rgba(255,255,255,.15);
    border:1px solid rgba(255,255,255,.28); border-radius:999px;
    padding:.14rem .72rem; font-size:.72rem; margin:.5rem .4rem 0 0; color:#eaf2f8; }
  div[data-testid="stMetric"] { background:#f6f9fc; border:1px solid #e3eaf1;
    border-radius:12px; padding:.7rem .95rem; }
  button[data-baseweb="tab"] { font-weight:600; }
  .stDownloadButton button, div[data-testid="stFormSubmitButton"] button {
    border-radius:10px; font-weight:650; }
  .pv-serious { background:#fdecea; color:#b3261e; border:1px solid #f3b4ad;
    padding:.5rem .85rem; border-radius:10px; font-weight:700; text-align:center; }
  .pv-ok { background:#e8f5ec; color:#1e7d3a; border:1px solid #aedcbb;
    padding:.5rem .85rem; border-radius:10px; font-weight:700; text-align:center; }
  .pv-card { background:#fff; border:1px solid #e3eaf1; border-radius:12px;
    padding:1rem 1.15rem; box-shadow:0 2px 10px rgba(16,36,62,.05); }
</style>
"""


def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, pills: list[str] | None = None) -> None:
    pills = pills or ["FDA FAERS 2026Q1", "RAG · 397K cases", "Groq LLM",
                      "ICH E2A seriousness"]
    pill_html = "".join(f"<span class='pv-pill'>{p}</span>" for p in pills)
    st.markdown(
        f"<div class='pv-hero'><h1>💊 {title}</h1><p>{subtitle}</p>"
        f"<div>{pill_html}</div></div>",
        unsafe_allow_html=True,
    )
