# ============================================================
# NewsLens backend - FastAPI + Uvicorn
# Multi-purpose image: runs the API and can host Alembic migrations.
# ============================================================
FROM python:3.14-slim AS base

# Fail loudly on pipe errors, keep apt output small.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libs:
#  - libpq5  : runtime for the psycopg (v3) PostgreSQL driver
#  - curl    : container HEALTHCHECK
#  - build-essential is intentionally NOT installed; requirements.txt pins
#    versions that ship binary wheels for cp314 (numpy/scipy/scikit-learn/
#    reportlab/psycopg[binary]), so no compiler is required.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code + migrations.
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Database defaults to SQLite in the container filesystem; override
# DATABASE_URL with a Postgres/Supabase URI for production.
ENV DATABASE_URL=sqlite:////app/data/newslens.db \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000
RUN mkdir -p /app/data

EXPOSE 8000

# Readiness probe (checks DB connectivity) - see app/api/routes/health.py.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${APP_PORT}/api/health/ready" || exit 1

# Single worker by default; scale with replicas/threads at the platform layer.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
