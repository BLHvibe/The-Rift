FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Phase 0d — copy every server module (main.py + db.py + api.py), not just main.
COPY *.py .

# v4.1.1 — version stamp baked into the image so `/api/engine/version` can
# return the git SHA the deployed binary was built from. Generated host-side
# before `fly deploy` (see scripts/draft_engine_audit.py + ENGINE_FIX_PLAN.md).
COPY version.txt .

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
