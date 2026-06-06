# 💊 Pharmacovigilance AI Copilot

A GenAI-powered Pharmacovigilance (PV) assistant that automates adverse-event
case analysis. Enter or upload an adverse-event narrative and the system extracts
safety entities, retrieves similar historical cases from the **FDA FAERS 2026Q1**
dataset via RAG, generates an AI case analysis (summary, seriousness, causality),
and produces a downloadable structured PV report.

Ships with **two frontends** (a multipage Streamlit app and a React SPA) over a
shared **FastAPI** backend, **switchable FAISS/Milvus** vector stores,
**switchable MiniLM/BioBERT** embeddings, **local SQLite persistence**, and
**rotating logs**.

## Pipeline

```
Input / Upload
   ↓  entity extraction (Groq LLM ⇄ FAERS-vocabulary rule fallback)
Extracted entities
   ↓  chunk → embed (MiniLM / BioBERT) → search (FAISS / Milvus) over 397K FAERS cases
Similar historical cases (RAG context)
   ↓  AI analysis (Native pipeline ⇄ LangChain LCEL chain)
AI summary · seriousness (ICH E2A) · causality · insights
   ↓
Structured PV report  →  PDF · Excel · JSON     (+ saved to SQLite)
```

## Architecture

| Layer | Files |
| --- | --- |
| **API (endpoints only)** | `main.py` (FastAPI) → delegates to `src/pipeline.py` |
| **Orchestration** | `src/pipeline.py` (extract → retrieve → analyze → report → persist) |
| **Streamlit UI** | `app.py` (Analyze), `pages/1_History.py`, `pages/2_Settings.py`, `src/ui_theme.py` |
| **React UI** | `frontend/` (Vite + React, proxies `/api` → FastAPI) |
| **Vector backends** | `src/vectordb.py` (dispatcher), `src/vector_store.py` (FAISS), `src/milvus_store.py` (Milvus) |
| **Embeddings / RAG** | `src/embeddings.py`, `src/rag.py`, `src/rag_langchain.py` |
| **NLP / analysis** | `src/extraction.py`, `src/analysis.py`, `src/seriousness.py`, `src/dictionaries.py` |
| **Reports** | `src/report.py` (PDF/Excel/JSON) |
| **Persistence / config** | `src/storage.py` (SQLite + uploads), `src/settings_store.py`, `config.py` |
| **Cross-cutting** | `src/logging_config.py` (rotating logs → `logs/`) |
| **Index build** | `scripts/build_index.py` |

## Quickstart (one command)

On a fresh machine, the bootstrap script sets up the venv, installs deps,
configures `.env`, lets you **choose what to embed** (minilm / biobert / both)
and the **backend** (faiss / milvus) — or shows where to drop prebuilt index
files if you already have them — then starts all services:

```bash
bash startup.sh                 # interactive
bash startup.sh --models both --backend milvus --start all -y   # non-interactive
```
> On Windows, run it from Git Bash. Re-running is safe — existing indexes are
> detected and reused. Prebuilt index files go in `data/`.

## 📦 Prebuilt indexes (download instead of building)

The FAERS vector indexes are large and **not** stored in git. Download the
prebuilt artifacts and drop them into `data/` to skip the embedding step:

**▶ Google Drive:** https://drive.google.com/drive/folders/1I-I-KqBcR3yM4kERajA9CdCbMmPaE-gY?usp=sharing

| File | Size | Needed for |
| --- | --- | --- |
| `faers_minilm.index` | ~582 MB | MiniLM retrieval (FAISS) |
| `faers_minilm_meta.parquet` | ~53 MB | MiniLM case metadata |
| `faers_biobert.index` | ~1.2 GB | BioBERT retrieval (FAISS) |
| `faers_biobert_meta.parquet` | ~53 MB | BioBERT case metadata |
| `drug_vocab.txt` | ~0.4 MB | offline rule-based NER |
| `reaction_vocab.txt` | ~0.15 MB | offline rule-based NER |

> Place **all** of these in the `data/` folder (≈1.9 GB total). You only need the
> pair(s) for the model(s) you intend to use. For the **Milvus** backend, after
> placing the FAISS files run `python scripts/faiss_to_milvus.py`
> (and `EMBED_MODEL_KEY=biobert python scripts/faiss_to_milvus.py`) to ingest —
> no re-embedding required.

## Manual setup

```powershell
pip install -r requirements.txt
copy .env.example .env          # paste GROQ_API_KEY (optional; rule-based without it)
#  ↳ or set the key later from the app's Settings page (React or Streamlit)

# Build the FAERS index (one-time). GPU strongly recommended.
python scripts/build_index.py                          # MiniLM (FAISS)
$env:EMBED_MODEL_KEY="biobert"; python scripts/build_index.py   # BioBERT (FAISS)
```

### Run the Streamlit app
```powershell
streamlit run app.py
```
Pages: **Analyze** · **History** (SQLite) · **Settings** (vector backend, model, engine).

### Run the FastAPI backend + React UI
```powershell
uvicorn main:app --reload --port 8000        # API at http://localhost:8000/docs
cd frontend; npm install; npm run dev        # React at http://localhost:5173
```

### Optional: Milvus vector backend (Windows → Docker)
```powershell
docker run -d --name milvus -p 19530:19530 milvusdb/milvus:latest milvus run standalone
$env:VECTOR_BACKEND="milvus"; python scripts/build_index.py    # ingest into Milvus
# then pick "milvus" on the Settings page (or set VECTOR_BACKEND=milvus)
```

## GPU acceleration
Embedding build auto-uses CUDA when a CUDA build of PyTorch is installed:
```powershell
pip install --force-reinstall --no-deps torch==2.12.0 --index-url https://download.pytorch.org/whl/cu126
```
On an RTX 4060 the 397K-case BioBERT build drops from ~3.5 h (CPU) to ~15 min.

## Design notes
- **Graceful degradation** — every AI step has a deterministic fallback; the app
  works with no API key, no Milvus, and no GPU.
- **Single source of truth** — `main.py` and Streamlit both call `pipeline.run_analysis`.
- **Cosine retrieval** — normalised vectors in inner-product indexes (FAISS & Milvus).
- **Auditability** — the ICH E2A rule engine always runs alongside the LLM; every
  run is persisted to SQLite with its settings.

> ⚠️ Decision-support only. Not a substitute for qualified medical review.
