# 💊 Pharmacovigilance AI Copilot

A GenAI-powered Pharmacovigilance (PV) assistant that automates adverse-event
case analysis. Enter or upload an adverse-event narrative and the system
extracts safety entities, retrieves similar historical cases from the **FDA
FAERS 2026Q1** dataset via RAG, generates an AI case analysis (summary,
seriousness, causality), and produces a downloadable structured PV report.

## Pipeline

```
Input / Upload
   ↓  entity extraction (Groq LLM ⇄ FAERS-vocabulary rule fallback)
Extracted entities
   ↓  chunk → embed (all-MiniLM-L6-v2) → FAISS search over ~397K FAERS cases
Similar historical cases (RAG context)
   ↓  LLM analysis grounded in retrieved cases
AI summary · seriousness (ICH E2A) · causality · insights
   ↓
Structured PV report  →  PDF · Excel · JSON
```

## Architecture

| Module | Responsibility |
| --- | --- |
| `config.py` | Paths, model names, env, FAERS code maps |
| `src/data_loader.py` | Join FAERS ASCII tables → per-case narratives |
| `src/dictionaries.py` | Drug/reaction vocab from FAERS (offline NER) |
| `src/extraction.py` | Entity extraction (LLM + rule fallback) |
| `src/chunking.py` | Sentence-aware text chunking |
| `src/embeddings.py` | sentence-transformers wrapper |
| `src/vector_store.py` | FAISS build / load / cosine search |
| `src/rag.py` | Retrieval + context assembly |
| `src/llm.py` | Groq client + robust JSON parsing |
| `src/seriousness.py` | ICH E2A / FAERS OUTC seriousness rules |
| `src/analysis.py` | AI case analysis (LLM + rule fallback) |
| `src/report.py` | Report schema + PDF / Excel / JSON export |
| `scripts/build_index.py` | One-time FAISS index build |
| `app.py` | Streamlit UI |

## Setup

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure the LLM (optional — app runs in rule-based mode without it)
copy .env.example .env       # then paste your GROQ_API_KEY

# 3. Build the FAERS RAG index (one-time; full dataset ≈ 397K cases)
python scripts/build_index.py
#   Quick smoke test instead:  $env:MAX_CASES=5000; python scripts/build_index.py

# 4. Launch the app
streamlit run app.py
```

## Design notes

- **Graceful degradation.** Every AI step has a deterministic fallback, so the
  app is fully functional with no API key — only the analysis quality changes.
- **Grounded extraction.** The offline NER vocabulary is derived from the same
  FAERS data the RAG index is built on, keeping extraction and retrieval aligned.
- **Cosine retrieval.** Embeddings are L2-normalised and stored in a FAISS
  inner-product index, so similarity scores are cosine similarities.
- **Seriousness cross-check.** The rule engine (ICH E2A outcome codes) always
  runs alongside the LLM and is surfaced in the report for auditability.

> ⚠️ Decision-support only. Not a substitute for qualified medical review.
