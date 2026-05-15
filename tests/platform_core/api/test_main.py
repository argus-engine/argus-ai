# SPDX-License-Identifier: Apache-2.0
"""Tests for the FastAPI ``/health`` placeholder."""

from __future__ import annotations

from fastapi.testclient import TestClient

from argus import __version__
from argus.platform_core.api.main import HealthResponse, app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "version": __version__,
        "service": "argus",
    }


def test_health_response_schema() -> None:
    """The Pydantic model defines exactly the contract the route serves."""
    fields = set(HealthResponse.model_fields.keys())
    assert fields == {"status", "version", "service"}


def test_app_metadata() -> None:
    assert app.title == "Argus"
    assert app.version == __version__
    assert app.openapi_url is not None  # OpenAPI docs available


def test_docs_endpoint_reachable() -> None:
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema_lists_health_route() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    assert "/health" in schema["paths"]
