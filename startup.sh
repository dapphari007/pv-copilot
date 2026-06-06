#!/usr/bin/env bash
# ============================================================================
#  startup.sh — one-command setup + launch for the Pharmacovigilance AI Copilot
#
#  Fresh system:   bash startup.sh
#  Non-interactive: bash startup.sh --models both --backend milvus --start all -y
#
#  What it does:
#    1. Creates a venv + installs Python deps
#    2. Sets up .env (GROQ_API_KEY)
#    3. Shows WHERE to place prebuilt indexes (or builds them — you choose the
#       embedding model: minilm / biobert / both, and backend: faiss / milvus)
#    4. Optionally starts FastAPI + Streamlit + React
#  Safe to re-run; existing indexes are detected and reused.
# ============================================================================
set -uo pipefail

# ---------- pretty output ----------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RED=$'\033[31m'
  BLU=$'\033[36m'; DIM=$'\033[2m'; RST=$'\033[0m'
else BOLD=; GRN=; YLW=; RED=; BLU=; DIM=; RST=; fi
say(){ printf '%s\n' "$*"; }
hd(){ printf '\n%s== %s ==%s\n' "$BOLD$BLU" "$*" "$RST"; }
ok(){ printf '%s✓%s %s\n' "$GRN" "$RST" "$*"; }
warn(){ printf '%s!%s %s\n' "$YLW" "$RST" "$*"; }
err(){ printf '%s✗%s %s\n' "$RED" "$RST" "$*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ---------- flags ----------
MODELS=""; BACKEND=""; DO_VENV=1; ASSUME_YES=0; START_SERVICES="ask"
usage(){ cat <<EOF
Usage: bash startup.sh [options]
  --models  minilm|biobert|both   embedding model(s) to build (else prompted)
  --backend faiss|milvus          vector backend (else prompted)
  --start   all|none              start services after setup (else prompted)
  --no-venv                       use the current Python env (skip .venv)
  -y, --yes                       accept defaults, no prompts
  -h, --help                      show this help
EOF
}
while [ $# -gt 0 ]; do
  case "$1" in
    --models)  MODELS="${2:-}"; shift 2;;
    --backend) BACKEND="${2:-}"; shift 2;;
    --start)   START_SERVICES="${2:-}"; shift 2;;
    --no-venv) DO_VENV=0; shift;;
    -y|--yes)  ASSUME_YES=1; shift;;
    -h|--help) usage; exit 0;;
    *) err "unknown argument: $1"; usage; exit 1;;
  esac
done

ask(){ # ask "prompt" "default" -> echoes answer
  local p="$1" d="${2:-}" ans
  if [ "$ASSUME_YES" = 1 ]; then printf '%s\n' "$d"; return; fi
  read -r -p "$p " ans </dev/tty 2>/dev/null || ans=""
  printf '%s\n' "${ans:-$d}"
}

printf '%s\n' "${BOLD}${BLU}"
say "  💊 Pharmacovigilance AI Copilot — setup"
printf '%s\n' "$RST"

# ---------- 1. Python ----------
hd "Python environment"
PY=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { err "Python 3.10+ not found. Please install Python first."; exit 1; }
ok "found $("$PY" --version 2>&1)"

if [ "$DO_VENV" = 1 ]; then
  [ -d .venv ] || { say "Creating virtual environment (.venv)…"; "$PY" -m venv .venv; }
  if   [ -f .venv/bin/activate ];     then . .venv/bin/activate
  elif [ -f .venv/Scripts/activate ]; then . .venv/Scripts/activate; fi
  PY=python
  ok "virtual environment active"
fi

say "Installing Python dependencies (this can take a few minutes on a fresh system)…"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install -r requirements.txt || { err "pip install failed"; exit 1; }
ok "dependencies installed"

# ---------- 2. .env ----------
hd "Configuration (.env)"
if [ ! -f .env ]; then
  [ -f .env.example ] && cp .env.example .env
  warn "Created .env from template."
  key="$(ask "Paste your GROQ_API_KEY (Enter to skip → rule-based fallback):" "")"
  if [ -n "$key" ]; then
    sed -i.bak "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$key|" .env && rm -f .env.bak
    ok "GROQ_API_KEY saved to .env"
  else warn "No key set — analysis will use the offline rule-based fallback."; fi
else ok ".env already present"; fi

# ---------- 3. Indexes ----------
DATA="$ROOT/data"; mkdir -p "$DATA"
hd "Vector indexes"
say "${BOLD}Index files belong here:${RST} $DATA"
say "${DIM}  Per model: faers_<model>.index + faers_<model>_meta.parquet${RST}"
say "${DIM}  Already have them? Copy those files into the folder above and re-run.${RST}"

have_faiss(){ [ -f "$DATA/faers_$1.index" ] && [ -f "$DATA/faers_${1}_meta.parquet" ]; }
for m in minilm biobert; do
  if have_faiss "$m"; then ok "FAISS index present: $m"; else say "${DIM}  · FAISS index missing: $m${RST}"; fi
done

NEED_BUILD=1
if have_faiss minilm || have_faiss biobert; then
  a="$(ask "Existing index found. Build/embed more anyway? [y/N]:" "n")"
  case "$a" in y|Y) NEED_BUILD=1;; *) NEED_BUILD=0; ok "Reusing existing indexes — skipping embedding.";; esac
fi

SEL_MODEL="minilm"; SEL_BACKEND="${BACKEND:-faiss}"
if [ "$NEED_BUILD" = 1 ]; then
  if [ ! -d "faers_ascii_2026q1/ASCII" ]; then
    err "FAERS dataset not found — cannot build."
    say "${BOLD}Place the FAERS ASCII files here:${RST} $ROOT/faers_ascii_2026q1/ASCII/"
    say "${DIM}  Files: DEMO/DRUG/REAC/OUTC/INDI/THER/RPSR + 26Q1.txt${RST}"
    say "${DIM}  Download: https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html${RST}"
    a="$(ask "Continue with existing indexes only? [Y/n]:" "y")"
    case "$a" in n|N) exit 1;; *) NEED_BUILD=0;; esac
  fi
fi

if [ "$NEED_BUILD" = 1 ]; then
  if [ -z "$MODELS" ]; then
    say ""; say "Which embedding model do you want to build?"
    say "  1) minilm  — all-MiniLM-L6-v2 (fast, 384d, general)"
    say "  2) biobert — S-BioBert (biomedical, 768d, slower)"
    say "  3) both"
    case "$(ask 'Select [1/2/3] (default 1):' 1)" in 2) MODELS=biobert;; 3) MODELS=both;; *) MODELS=minilm;; esac
  fi
  if [ -z "$BACKEND" ]; then
    say ""; say "Which vector backend?"
    say "  1) faiss  — local files, no server (default)"
    say "  2) milvus — Milvus server via Docker"
    case "$(ask 'Select [1/2] (default 1):' 1)" in 2) BACKEND=milvus;; *) BACKEND=faiss;; esac
  fi
  SEL_BACKEND="$BACKEND"

  build_one(){
    if have_faiss "$1"; then ok "FAISS $1 already built — skipping"; else
      say "Building FAISS index: ${BOLD}$1${RST} (slow on CPU; fast on GPU)…"
      EMBED_MODEL_KEY="$1" "$PY" scripts/build_index.py || { err "build failed for $1"; exit 1; }
    fi
  }
  case "$MODELS" in
    both)    build_one minilm; build_one biobert; SEL_MODEL=biobert;;
    biobert) build_one biobert; SEL_MODEL=biobert;;
    *)       build_one minilm;  SEL_MODEL=minilm;;
  esac

  if [ "$BACKEND" = milvus ]; then
    command -v docker >/dev/null 2>&1 || { err "Docker is required for the Milvus backend."; exit 1; }
    say "Starting Milvus (Docker Compose)…"
    docker compose -f docker-compose.milvus.yml up -d || { err "Milvus failed to start"; exit 1; }
    say "Waiting for Milvus to become healthy…"
    for _ in $(seq 1 40); do
      [ "$(docker inspect -f '{{.State.Health.Status}}' pv-milvus-standalone 2>/dev/null || echo none)" = healthy ] && { ok "Milvus healthy"; break; }
      sleep 3
    done
    for m in $( [ "$MODELS" = both ] && echo "minilm biobert" || echo "$MODELS" ); do
      say "Ingesting $m into Milvus…"
      EMBED_MODEL_KEY="$m" "$PY" scripts/faiss_to_milvus.py || { err "Milvus ingest failed for $m"; exit 1; }
    done
  fi
fi

# persist chosen defaults so the UI/API start on the right backend+model
"$PY" - "$SEL_BACKEND" "$SEL_MODEL" <<'PYEOF' || true
import sys
from src.settings_store import save_settings
save_settings({"vector_backend": sys.argv[1], "embedding_model": sys.argv[2]})
print(f"default settings -> backend={sys.argv[1]} model={sys.argv[2]}")
PYEOF
ok "Setup complete."

# ---------- 4. Services ----------
hd "Start services"
if [ "$START_SERVICES" = "ask" ]; then
  case "$(ask 'Start API + Streamlit + React now? [Y/n]:' y)" in n|N) START_SERVICES=none;; *) START_SERVICES=all;; esac
fi

if [ "$START_SERVICES" = "all" ]; then
  mkdir -p logs
  say "Starting FastAPI on :8000…"
  nohup "$PY" -m uvicorn main:app --host 0.0.0.0 --port 8000 >logs/api.out 2>&1 &
  say "Starting Streamlit on :8501…"
  nohup "$PY" -m streamlit run app.py --server.headless true --server.port 8501 >logs/streamlit.out 2>&1 &
  if command -v npm >/dev/null 2>&1; then
    ( cd frontend && [ -d node_modules ] || { say "Installing frontend deps…"; npm install; } )
    say "Starting React on :5173…"
    ( cd frontend && nohup npm run dev >"$ROOT/logs/react.out" 2>&1 & )
  else
    warn "npm not found — skipping React UI (install Node 18+ to enable it)."
  fi
  sleep 2
  hd "Ready"
  ok "API:       http://localhost:8000/docs"
  ok "Streamlit: http://localhost:8501"
  ok "React:     http://localhost:5173"
  say "${DIM}Logs: logs/pv_copilot.log (app) · logs/*.out (per service)${RST}"
else
  hd "Run manually"
  say "  $PY -m uvicorn main:app --port 8000"
  say "  $PY -m streamlit run app.py"
  say "  (cd frontend && npm install && npm run dev)"
fi
