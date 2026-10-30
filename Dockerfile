# syntax=docker/dockerfile:1

# Python 3.12 on Debian Trixie; update the readable tag and digest together.
# See docs/deployment.md for the base-image update and qualification process.
ARG PYTHON_IMAGE=python:3.12.16-slim-trixie@sha256:8523d6abeb48ceae0b7240d30c5808fc26cb79c1a635bacdf19cf3baecfbec07

# ---------- Build stage ----------
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.txt \
 && /opt/venv/bin/python -m pip check

# ---------- Runtime stage ----------
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

COPY app ./app
COPY alembic.ini ./alembic.ini

# Code and dependencies remain root-owned and readable by the application user.
USER 10001:10001
EXPOSE 8000

CMD ["python", "-m", "app.main"]
