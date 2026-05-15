# SPDX-License-Identifier: Apache-2.0
# syntax=docker/dockerfile:1.7

# ============================================================================
# Argus multi-stage Dockerfile.
#
# Final targets:
#   - cpu       (default) — python:3.12-slim-bookworm, FastAPI service
#   - gpu                 — nvidia/cuda:12.4.1-runtime-ubuntu22.04 + Python 3.12
#   - streamlit           — FROM cpu, adds the streamlit extra + frontend
#
# Build invocations:
#   docker build -t argus:cpu       --target cpu       -f infra/docker/Dockerfile .
#   docker build -t argus:gpu       --target gpu       -f infra/docker/Dockerfile .
#   docker build -t argus:streamlit --target streamlit -f infra/docker/Dockerfile .
#
# Layer ordering rules (do not change without re-checking the cache impact):
#   1. OS package installs (rarely change)
#   2. Virtualenv creation
#   3. Project metadata (pyproject.toml, argus/__init__.py only — the bare
#      minimum the editable install needs to resolve)
#   4. Python dependency install
#   5. Source code copy (changes most often, lands last)
#
# Code-only changes never bust the dep-install cache, so iterative builds
# during development are sub-second on the warm cache.
#
# Base image pinning is currently to MAJOR.MINOR.PATCH tags. Promoting to
# `image@sha256:<digest>` pins is a Phase 6 polish item (the digests aren't
# stable across regional registries and the Phase-5 image-push workflow is
# where the canonical digest will be authored).
# ============================================================================

ARG PYTHON_VERSION=3.12.7
ARG CUDA_VERSION=12.4.1

# ============================================================================
# Stage: builder-cpu — install Python dependencies on the slim base
# ============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder-cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Project metadata only — the bare minimum needed to resolve and install the
# Argus package itself in editable mode without copying its source yet. The
# argus/__init__.py is required because hatchling reads __version__ from it.
COPY pyproject.toml ./
COPY README.md ./
COPY argus/__init__.py ./argus/__init__.py

RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip \
    && pip install -e .

# ============================================================================
# Stage: cpu — default runtime image (FastAPI service)
# ============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    ARGUS_LOG_LEVEL=INFO

# Runtime utilities only. curl is required by HEALTHCHECK. No build-essential.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 argus \
    && useradd  --system --uid 1000 --gid argus --shell /bin/bash --create-home argus

COPY --from=builder-cpu --chown=argus:argus /opt/venv /opt/venv

WORKDIR /app
COPY --chown=argus:argus pyproject.toml README.md ./
COPY --chown=argus:argus argus   ./argus
COPY --chown=argus:argus configs ./configs

USER argus

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

CMD ["uvicorn", "argus.platform_core.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================================
# Stage: builder-gpu — install Python on the CUDA runtime, then install deps
# ============================================================================
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu22.04 AS builder-gpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# ubuntu22.04 ships Python 3.10. We need 3.12, so we pull it from the
# deadsnakes PPA — a long-standing community archive for current Python
# versions on older Ubuntu LTSs.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        gnupg \
        software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        python3.12 \
        python3.12-dev \
        python3.12-venv \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml ./
COPY README.md ./
COPY argus/__init__.py ./argus/__init__.py

# Base install only for now. The [ml] extra (torch, transformers, etc.) is
# added in Phase 3 once an actual predictive head needs it; pre-installing
# multi-GB ML libraries on every CI build would otherwise slow Phase 1 down.
RUN python3.12 -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip \
    && pip install -e .

# ============================================================================
# Stage: gpu — NVIDIA-capable runtime image (FastAPI service, GPU-ready)
# ============================================================================
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu22.04 AS gpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    ARGUS_LOG_LEVEL=INFO

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        gnupg \
        software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        python3.12 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 argus \
    && useradd  --system --uid 1000 --gid argus --shell /bin/bash --create-home argus

COPY --from=builder-gpu --chown=argus:argus /opt/venv /opt/venv

WORKDIR /app
COPY --chown=argus:argus pyproject.toml README.md ./
COPY --chown=argus:argus argus   ./argus
COPY --chown=argus:argus configs ./configs

USER argus

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

CMD ["uvicorn", "argus.platform_core.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================================
# Stage: streamlit — placeholder reviewer dashboard, layered on top of cpu
# ============================================================================
FROM cpu AS streamlit

USER root

# Add the streamlit extra to the existing venv. Done as root because the
# /opt/venv site-packages is owned by argus but pip needs to drop files
# in there; switching back to argus after.
RUN /opt/venv/bin/pip install --no-cache-dir "streamlit>=1.37"

COPY --chown=argus:argus frontend ./frontend

USER argus

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl --fail --silent http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
