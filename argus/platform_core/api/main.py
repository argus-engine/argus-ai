# SPDX-License-Identifier: Apache-2.0
"""FastAPI application entrypoint.

Phase 1 surface: a single ``/health`` endpoint so the Dockerfile's
``HEALTHCHECK`` instruction and the docker-compose stack have something
concrete to probe end-to-end. The application stays deliberately minimal —
business logic lives behind the layered ``platform_core`` modules, and
``/predict`` / ``/explain`` / HITL routes land in Phase 3+.

Run locally:

    uvicorn argus.platform_core.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from argus import __version__

app = FastAPI(
    title="Argus",
    version=__version__,
    summary="Multimodal, explainable, uncertainty-aware risk intelligence.",
    docs_url="/docs",
    redoc_url="/redoc",
)


class HealthResponse(BaseModel):
    """Response shape for the ``/health`` endpoint."""

    status: str
    version: str
    service: str


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness probe.

    Reachable without auth (auth lands no earlier than Phase 5). Used by the
    container ``HEALTHCHECK`` instruction and by the Streamlit placeholder
    to verify the API is up.
    """
    return HealthResponse(status="ok", version=__version__, service="argus")
