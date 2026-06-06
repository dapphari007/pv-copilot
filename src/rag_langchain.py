"""LangChain-orchestrated RAG path (alternative to the native pipeline).

This wires the *same* FAERS FAISS index and Groq backend through LangChain:

* ``FaersRetriever`` — a custom ``BaseRetriever`` that runs our cosine search and
  returns LangChain ``Document`` objects (no giant in-memory docstore needed).
* ``analyze_case_langchain`` — an LCEL chain
  ``retriever → prompt → ChatGroq → JSON`` producing the same analysis schema.

It is selectable from the UI and degrades gracefully if LangChain / the API key
are unavailable.
"""
from __future__ import annotations

from typing import Any

import config
from src import analysis as analysis_mod
from src import embeddings, vectordb


def langchain_available() -> bool:
    try:
        import langchain_core  # noqa: F401
        import langchain_groq  # noqa: F401
    except Exception:
        return False
    return config.llm_available()


def _make_retriever(model_key: str, top_k: int, backend: str | None = None):
    """Build a LangChain retriever backed by our vector-DB dispatcher (FAISS/Milvus)."""
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever

    class FaersRetriever(BaseRetriever):
        model_key: str = "minilm"
        top_k: int = 5
        backend: str | None = None

        def _get_relevant_documents(self, query: str, *, run_manager=None):
            vector = embeddings.embed_query(query, model_key=self.model_key)
            hits = vectordb.search(vector, self.model_key, top_k=self.top_k,
                                   backend=self.backend)
            return [
                Document(
                    page_content=h.get("narrative", ""),
                    metadata={
                        "primaryid": h.get("primaryid", ""),
                        "similarity": h.get("similarity", 0.0),
                        "seriousness": h.get("seriousness", ""),
                    },
                )
                for h in hits
            ]

    return FaersRetriever(model_key=model_key, top_k=top_k, backend=backend)


def analyze_case_langchain(
    narrative: str,
    entities: dict[str, Any],
    model_key: str | None = None,
    top_k: int | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    """Run analysis via a LangChain LCEL chain; returns analysis + retrieved cases."""
    model_key = model_key or config.DEFAULT_MODEL_KEY
    top_k = top_k or config.TOP_K

    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_groq import ChatGroq

    retriever = _make_retriever(model_key, top_k, backend)
    docs = retriever.invoke(narrative)
    retrieved = [
        {
            "primaryid": d.metadata.get("primaryid", ""),
            "similarity": d.metadata.get("similarity", 0.0),
            "seriousness": d.metadata.get("seriousness", ""),
            "narrative": d.page_content,
        }
        for d in docs
    ]

    context = "\n\n".join(
        f"[Case {i} | id={d.metadata.get('primaryid', '?')} | "
        f"similarity={float(d.metadata.get('similarity', 0.0)):.2f}]\n{d.page_content}"
        for i, d in enumerate(docs, start=1)
    ) or "No similar historical cases were retrieved."

    entity_lines = "\n".join(f"- {k}: {v}" for k, v in entities.items() if v)

    llm = ChatGroq(
        model=config.GROQ_MODEL,
        api_key=config.GROQ_API_KEY,
        temperature=config.LLM_TEMPERATURE,
        max_tokens=config.LLM_MAX_TOKENS,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", analysis_mod.ANALYSIS_SYSTEM), ("human", "{user}")]
    )
    chain = prompt | llm | JsonOutputParser()
    user = analysis_mod.ANALYSIS_TEMPLATE.format(
        narrative=narrative.strip(),
        entities=entity_lines or "None extracted.",
        context=context,
    )
    data = chain.invoke({"user": user})
    analysis = analysis_mod.finalize(
        data, narrative, entities, retrieved, source="langchain"
    )
    return {"analysis": analysis, "retrieved": retrieved}
