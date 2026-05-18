# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for the Argus test suite.

Layer-specific fixtures live alongside that layer's tests. Fixtures
that span multiple test layers — currently the KG backend fixtures,
shared between :mod:`tests.platform_core.kg` and
:mod:`tests.domain_packs.supply_chain.kg` — live here so the heavy
session-scoped Neo4j container is built once per pytest run, not once
per consuming directory. Cross-cutting environment shims (color, time,
fixtures-dir) also live here.

testcontainers is lazy-imported inside the Neo4j fixture bodies so this
module stays importable on a base ``[dev]`` install — collection
happens before marker filtering, so a top-level
``import testcontainers`` would force every consumer of the conftest
to carry testcontainers in their environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from argus.platform_core.kg import (
    KGBackendConfig,
    NetworkXBackend,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from argus.platform_core.kg.base import KGBackend


_NEO4J_IMAGE = "neo4j:5.20.0-community"
_NEO4J_TEST_PASSWORD = "test-password"


# ---------------------------------------------------------------------------
# Cross-cutting environment shims
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the committed test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _disable_cli_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force plain (uncoloured) CLI output for cross-platform test stability.

    Typer (and the Rich renderer it pulls in) emit ANSI colour escapes when
    they detect a colour-capable terminal. On Linux CI runners and most
    Linux developer terminals this is the default, so ``CliRunner`` captures
    output like ``\\x1b[1m--host\\x1b[0m`` instead of plain ``--host``.
    Windows terminals typically don't trigger the colour path, so substring
    assertions on ``--help`` output pass locally and break on CI.

    The fix is the cross-stack opt-out standard from https://no-color.org —
    setting ``NO_COLOR`` to any non-empty value tells Typer / Rich / Click
    to skip colour, and ``CliRunner`` then captures the exact same plain
    text on every platform.

    Autouse + function-scoped so every test gets a clean env without
    needing to wire the fixture into its signature. Setting it for non-CLI
    tests is harmless — they don't read it.
    """
    monkeypatch.setenv("NO_COLOR", "1")


# ---------------------------------------------------------------------------
# KG backend fixtures (cross-cutting across kg test layers)
# ---------------------------------------------------------------------------
#
# TODO(kg-testing): migrate to testcontainers' structured wait-strategy API
# (HttpWaitStrategy / LogMessageWaitStrategy) once they remove the deprecated
# @wait_container_is_ready decorator. The matching ignore-filter in
# pyproject.toml suppresses the deprecation that fires from inside the Neo4j
# fixture today; remove the filter at the same time as this migration.


def _new_neo4j_container(*, with_apoc: bool) -> Any:
    """Construct a configured but not-yet-started Neo4j container."""
    from testcontainers.neo4j import Neo4jContainer

    container = Neo4jContainer(_NEO4J_IMAGE, password=_NEO4J_TEST_PASSWORD)
    if with_apoc:
        container = (
            container.with_env("NEO4J_PLUGINS", '["apoc"]')
            .with_env("NEO4J_dbms_security_procedures_unrestricted", "apoc.*")
            .with_env("NEO4J_dbms_security_procedures_allowlist", "apoc.*")
            .with_env("NEO4J_apoc_export_file_enabled", "true")
            .with_env("NEO4J_apoc_import_file_enabled", "true")
        )
    return container


@pytest.fixture(scope="session")
def neo4j_container() -> Iterator[Any]:
    """Spin up Neo4j 5.20-community + APOC once per session."""
    container = _new_neo4j_container(with_apoc=True)
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def neo4j_no_apoc_container() -> Iterator[Any]:
    """Spin up a vanilla Neo4j 5.20-community (no APOC) for the missing-plugin test."""
    container = _new_neo4j_container(with_apoc=False)
    container.start()
    try:
        yield container
    finally:
        container.stop()


def _neo4j_config(container: Any, *, name: str = "neo4j-test") -> KGBackendConfig:
    from pydantic import SecretStr

    return KGBackendConfig(
        name=name,
        neo4j_uri=container.get_connection_url(),
        neo4j_user="neo4j",
        neo4j_password=SecretStr(_NEO4J_TEST_PASSWORD),
    )


@pytest.fixture
def neo4j_backend(neo4j_container: Any) -> Iterator[KGBackend]:
    """Function-scoped Neo4jBackend pointing at the session container; cleared per test."""
    from argus.platform_core.kg.neo4j_backend import Neo4jBackend

    backend = Neo4jBackend(_neo4j_config(neo4j_container))
    backend.connect()
    backend.clear()
    try:
        yield backend
    finally:
        backend.disconnect()


@pytest.fixture
def networkx_backend() -> Iterator[KGBackend]:
    """Function-scoped NetworkXBackend, connected and empty."""
    backend = NetworkXBackend(KGBackendConfig(name="nx-test"))
    backend.connect()
    try:
        yield backend
    finally:
        backend.disconnect()


@pytest.fixture(
    params=[
        "networkx",
        pytest.param("neo4j", marks=[pytest.mark.integration]),
    ],
)
def backend(request: pytest.FixtureRequest) -> KGBackend:
    """Parametrised backend fixture used by every cross-backend test.

    The ``neo4j`` parameter carries the ``integration`` marker so a
    default ``pytest`` run (which excludes ``-m integration``) only
    exercises the NetworkX variant. ``pytest -m integration`` flips it.
    """
    fixture_name = "networkx_backend" if request.param == "networkx" else "neo4j_backend"
    fixture_value: KGBackend = request.getfixturevalue(fixture_name)
    return fixture_value
