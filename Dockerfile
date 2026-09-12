# Hugging Face Space image: one process, one port.
#
# The frontend is exported to static files and served by the API, so the page and
# the API share an origin and there is no CORS configuration to get wrong in a
# place nobody can debug.
#
# The corpus ships in the image rather than being fetched at boot. bdlaws has been
# unreachable during this project more than once, and a legal assistant that
# starts with no statute is worse than one that does not start: it would answer
# from the model's memory, which is the failure the whole system exists to prevent.

# --- frontend -----------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- runtime ------------------------------------------------------------------
FROM python:3.12-slim

# tesseract backs the image-input path. Without it the feature degrades to a
# clear "OCR is not available" rather than failing, but a demo that cannot read
# an image is not demonstrating image input. English and Bengali only — the
# languages the corpus and its questions are in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-ben \
    && rm -rf /var/lib/apt/lists/*

# Spaces runs containers as uid 1000. Everything written at runtime has to be
# owned by it, the embedding-model cache included.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:/home/user/app/backend/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    EMBEDDING_CACHE_DIR=/home/user/.cache/fastembed
WORKDIR /home/user/app

RUN pip install --no-cache-dir --user uv

# Installed from the lockfile, not resolved fresh. A deployment that resolves its
# own dependencies is a deployment running something nobody tested.
COPY --chown=user backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project

COPY --chown=user backend/ ./backend/
COPY --chown=user --from=web /build/out ./backend/static

# The corpus and the prebuilt index sit beside backend/, which is where the code
# resolves them from.
COPY --chown=user data/raw ./data/raw
COPY --chown=user data/index/legal_aware_schedule ./data/index/legal_aware_schedule

# Pull the embedding model into the image, into the directory the application
# reads at runtime. fastembed's own default is under the system temp path, which
# a host is free to hand back empty on every cold start — so the location is set
# explicitly on both sides rather than left to a default that happens to work on
# a laptop.
WORKDIR /home/user/app/backend
RUN python -c "from app.retrieval.embeddings import _model, DEFAULT_MODEL; _model(DEFAULT_MODEL)" \
    && test -d "$EMBEDDING_CACHE_DIR" 

WORKDIR /home/user/app

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "7860", \
     "--app-dir", "/home/user/app/backend"]
