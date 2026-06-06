# 🚀 Deployment Guide — Pharmacovigilance AI Copilot

This app is a multi-service stack: **FastAPI** (API), **Streamlit** (UI), **React**
(UI), and a **vector DB** (FAISS files *or* Milvus), backed by **~1.8 GB of
prebuilt FAERS indexes**. This guide covers how to ship it.

> **GPU is NOT required to deploy.** The GPU only accelerates *building* the
> index. Serving (embedding one query + searching) runs fine on CPU.

---

## 0. Prerequisites (do this once, anywhere)

1. **Build the indexes** (or copy them from your machine). They live in `data/`:
   - `data/faers_minilm.index` (~610 MB) + `data/faers_minilm_meta.parquet`
   - `data/faers_biobert.index` (~1.2 GB) + `data/faers_biobert_meta.parquet`
   ```bash
   python scripts/build_index.py                      # minilm
   EMBED_MODEL_KEY=biobert python scripts/build_index.py   # biobert
   ```
2. **Secrets:** set `GROQ_API_KEY` in the host environment / platform secrets.
   Never bake it into an image (already in `.dockerignore` / `.gitignore`).

### The index-hosting decision (the main deployment question)
The `data/` indexes are too big for a git repo / container image. Pick one:
- **A. Ship as a volume** — copy `data/` to the server, mount it (compose does this).
- **B. Object storage** — upload `data/` to S3/R2/GCS, download on container start.
- **C. Rebuild on the host** — only if the host has the FAERS raw files + time/RAM.

---

## Option A — Docker Compose on a single VM  ⭐ recommended

Mirrors local exactly; Milvus runs alongside the app.

**Host sizing:** 4–8 GB RAM, 2 vCPU, ~6 GB free disk (indexes + Milvus volumes).

```bash
# On the VM (Docker + Compose installed):
git clone <your-repo> && cd "PV Copilot"
# copy your prebuilt data/ indexes onto the VM (scp/rsync/object storage)
echo "GROQ_API_KEY=sk-..." > .env

docker compose up -d --build       # brings up milvus + api + streamlit + frontend
```

Services (publish/proxy as needed behind a reverse proxy + TLS):
- API → `:8000` · Streamlit → `:8501` · React (nginx) → `:5173` · Milvus → `:19530`

**One-time after Milvus is up** (if using the milvus backend), ingest the index:
```bash
docker compose exec api python scripts/faiss_to_milvus.py
docker compose exec api env EMBED_MODEL_KEY=biobert python scripts/faiss_to_milvus.py
```

**Production hardening:**
- Put **nginx/Caddy/Traefik** in front for HTTPS + a single domain
  (e.g. `/` → React, `/api` → FastAPI, `/app` → Streamlit).
- Add `restart: unless-stopped` to each service.
- Default `VECTOR_BACKEND=faiss` needs no Milvus — drop the milvus services if
  you don't need it (smaller footprint).

---

## Option B — Split / managed services

| Piece | Platform | Notes |
| --- | --- | --- |
| **React** | Vercel / Netlify / Cloudflare Pages | `cd frontend && npm run build` → deploy `dist/`. Set the API base URL (proxy `/api` → your API host). |
| **FastAPI** | Render / Railway / Fly.io | Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`. Mount/download the `data/` indexes; set `GROQ_API_KEY`. |
| **Milvus** | **Zilliz Cloud** (managed) | Set `MILVUS_URI` + `MILVUS_TOKEN`, then run `faiss_to_milvus.py` once to ingest. Or use `VECTOR_BACKEND=faiss` and skip Milvus entirely. |
| **Indexes** | S3 / Cloudflare R2 / GCS | Download into `data/` on container start (add a small entrypoint script). |

CORS is already open in `main.py` (`allow_origins=["*"]`) — tighten it to your
frontend domain in production.

---

## Option C — Streamlit Community Cloud (UI-only, quickest)

Free, but **cannot run Milvus** and has limited disk — so use **FAISS** and a
**single model** (minilm) to stay small.
1. Point `app.py` as the entrypoint; set `GROQ_API_KEY` in *Secrets*.
2. Host `data/faers_minilm.index` + meta via object storage and download on
   startup (the 610 MB file is too big to commit).
3. Set `VECTOR_BACKEND=faiss`, `EMBED_MODEL_KEY=minilm`.

---

## Environment variables (reference)

| Var | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | — | LLM analysis (omit → rule-based fallback) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model id |
| `VECTOR_BACKEND` | `faiss` | `faiss` or `milvus` |
| `MILVUS_URI` | `http://localhost:19530` | Milvus server / Zilliz endpoint |
| `MILVUS_TOKEN` | — | Zilliz Cloud / auth |
| `EMBED_MODEL_KEY` | `minilm` | `minilm` or `biobert` |

> ⚠️ Decision-support only — not a medical device. Add appropriate disclaimers
> and access controls before any real-world use.
