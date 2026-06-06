"""Settings page — configure the vector backend, embedding model, and RAG engine.

Replaces the old sidebar selectors. Writes to ``settings_store`` (settings.json),
which the Analyze page and the API both read.
"""
from __future__ import annotations

import streamlit as st

import config
from src import milvus_store, rag_langchain, vectordb
from src.settings_store import load_settings, save_settings
from src.ui_theme import hero, inject_theme

st.set_page_config(page_title="PV Copilot · Settings", page_icon="⚙️", layout="wide")
inject_theme()
hero("Settings", "Choose the vector database, embedding model, and RAG engine. "
                 "Changes apply to every new analysis.", pills=["Runtime config"])

settings = load_settings()
status = vectordb.backend_status()

# --- diagnostics ---
st.markdown("#### System diagnostics")
d1, d2, d3, d4 = st.columns(4)
d1.metric("Groq LLM", "available" if config.llm_available() else "fallback")
d2.metric("FAISS models", len(status["faiss_models"]))
d3.metric("Milvus installed", "yes" if status["milvus_installed"] else "no")
d4.metric("LangChain", "ready" if rag_langchain.langchain_available() else "no")

st.divider()

with st.form("settings_form"):
    st.markdown("#### Vector database")
    backend = st.radio(
        "Backend", options=list(config.VECTOR_BACKENDS),
        index=list(config.VECTOR_BACKENDS).index(settings["vector_backend"]),
        horizontal=True,
        help="FAISS = local file index (default). Milvus = server (needs MILVUS_URI; "
             "on Windows run Milvus via Docker).",
    )
    if backend == "milvus" and not status["milvus_installed"]:
        st.warning("`pymilvus` is not installed. Run `pip install pymilvus`.")
    if backend == "milvus":
        st.caption(f"Milvus URI: `{config.MILVUS_URI}` · "
                   f"collections built: {status['milvus_models'] or 'none'}")

    st.markdown("#### Embedding model")
    model_keys = list(config.EMBEDDING_MODELS)
    built = set(vectordb.available_models(backend))
    model = st.selectbox(
        "Model", options=model_keys,
        index=model_keys.index(settings["embedding_model"])
        if settings["embedding_model"] in model_keys else 0,
        format_func=lambda k: config.EMBEDDING_MODELS[k]["label"]
        + ("  ✅ built" if k in built else "  ⏳ not built"),
    )

    st.markdown("#### RAG engine")
    engines = ["Native"] + (["LangChain"] if rag_langchain.langchain_available() else [])
    engine = st.radio(
        "Engine", options=engines,
        index=engines.index(settings["rag_engine"]) if settings["rag_engine"] in engines else 0,
        horizontal=True,
    )

    top_k = st.slider("Similar cases to retrieve (Top-K)", 1, 15, int(settings["top_k"]))

    if st.form_submit_button("💾 Save settings", type="primary"):
        new = save_settings({
            "vector_backend": backend, "embedding_model": model,
            "rag_engine": engine, "top_k": top_k,
        })
        st.success("Settings saved.")
        st.json(new)

st.divider()
with st.expander("ℹ️ How to build an index for the selected model/backend"):
    st.code(
        "# FAISS (default):\n"
        "python scripts/build_index.py                 # minilm\n"
        '$env:EMBED_MODEL_KEY="biobert"; python scripts/build_index.py\n\n'
        "# Milvus (start the server first):\n"
        "docker run -d --name milvus -p 19530:19530 milvusdb/milvus:latest "
        "milvus run standalone\n"
        '$env:VECTOR_BACKEND="milvus"; python scripts/build_index.py',
        language="powershell",
    )
