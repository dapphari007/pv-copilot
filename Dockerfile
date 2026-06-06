# Python application image — serves BOTH the FastAPI backend and the Streamlit
# UI (the CMD is overridden per service in docker-compose.yml).
#
# Build:  docker build -t pv-copilot .
# The prebuilt FAERS index, uploads, and logs are mounted as volumes at runtime
# (see docker-compose.yml) — they are intentionally NOT baked into the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache

WORKDIR /app

# System deps for faiss / reportlab / pdf parsing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# FastAPI (8000) and Streamlit (8501); compose chooses which to run.
EXPOSE 8000 8501

# Default command runs the API; the streamlit service overrides this.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
