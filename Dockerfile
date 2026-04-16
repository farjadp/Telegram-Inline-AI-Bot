# ============================================================================
# Source: Dockerfile
# Version: 1.0.0 — 2026-04-16
# Why: Multi-stage Python 3.11 container for the FastAPI app and Celery worker
# Env / Identity: Docker — Python 3.11-slim
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install all Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies needed for psycopg2 and other compiled packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (Docker layer caching — only rebuilds when deps change)
COPY requirements.txt .

# Install Python packages into a prefix directory for clean copy
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime — lean production image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Install only runtime system deps (no build tools)
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app

USER botuser

# Expose FastAPI port
EXPOSE 8000

# Default command — can be overridden in docker-compose.yml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
