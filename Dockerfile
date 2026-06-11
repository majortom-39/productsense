# ProductSense API — Cloud Run image (built from the repo ROOT so the shared
# packages/prompts/*.md persona files are available to the backend).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Deps first for layer caching. psycopg[binary] bundles libpq; cryptography ships
# manylinux wheels — no apt build toolchain needed on slim.
COPY apps/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend source (includes app/deepagent/knowledge: the skill + memory files).
COPY apps/api/ ./
# Shared persona prompts live outside apps/api in the monorepo — vendor them in.
COPY packages/prompts/ /app/packages/prompts/
ENV PROMPTS_DIR=/app/packages/prompts

# Cloud Run injects $PORT (default 8080).
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
