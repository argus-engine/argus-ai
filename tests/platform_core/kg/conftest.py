# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the knowledge-graph test suite.

The Neo4j fixtures lazy-import :mod:`testcontainers` and the Neo4j
driver inside their bodies so this conftest stays importable on a base
``[dev]`` install — collection happens before marker filtering, so a
top-level ``import testcontainers`` would force the dev extras to carry
testcontainers even when the integration suite is not being run.

Fixtures provided:

- ``neo4j_container`` (session) — a Neo4j 5.20-community container with
  APOC enabled. One container per session; tests run serially against
  it and reset state via ``backend.clear()``.
- ``neo4j_no_apoc_container`` (session) — a second container without
  APOC, used by the connection-time APOC-availability check test.
- ``neo4j_backend`` (function) — a connected, cleared Neo4jBackend
  pointing at the session container.
- ``networkx_backend`` (function) — a connected NetworkXBackend.
- ``backend`` (function, parametrised over ``["networkx", "neo4j"]``)
  — the parametrised fixture parity tests run against. The Neo4j
  parameter carries the ``integration`` marker so default ``pytest``
  runs only the NetworkX variant.
- ``supply_chain`` (function) — builds the canonical mini supply-chain
  graph on whichever backend the test is parametrised with and returns
  a dict of node-id shortcuts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from argus.platform_core.kg import (
    EdgeType,
    KGBackendConfig,
    KGEdge,
    KGNode,
    NetworkXBackend,
    NodeType,
    make_edge_id,
    make_node_id,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from argus.platform_core.kg.base import KGBackend


_NEO4J_IMAGE = "neo4j:5.20.0-community"
_NEO4J_TEST_PASSWORD = "test-password"


# ---------------------------------------------------------------------------
# Mini supply-chain graph
# ---------------------------------------------------------------------------


def _build_supply_chain(backend: KGBackend) -> dict[str, str]:
    """Build the canonical mini supply-chain graph on ``backend``.

    Layout (FK orientation; BFS in the backends walks both directions)::

        Supplier:S1 -LOCATED_IN-> Region:APAC
        Supplier:S2 -LOCATED_IN-> Region:NA
        Product:P1  -DEPENDS_ON-> Supplier:S1
        Product:P2  -DEPENDS_ON-> Supplier:S2
        Order:O1    -HAS_SUPPLIER-> Supplier:S1
        Order:O1    -PLACED_BY-> Customer:C1
        Order:O1    -OF_PRODUCT-> Product:P1
        Order:O2    -HAS_SUPPLIER-> Supplier:S1
        Order:O2    -PLACED_BY-> Customer:C2
        Order:O2    -OF_PRODUCT-> Product:P2
        Shipment:SH1 -FULFILS_ORDER-> Order:O1
        Shipment:SH1 -SUPPLIED_BY-> Supplier:S1
        Shipment:SH1 -SHIPS_TO-> Region:NA
    """
    ids: dict[str, str] = {
        "S1": make_node_id(NodeType.SUPPLIER, "S1"),
        "S2": make_node_id(NodeType.SUPPLIER, "S2"),
        "APAC": make_node_id(NodeType.REGION, "APAC"),
        "NA": make_node_id(NodeType.REGION, "NA"),
        "C1": make_node_id(NodeType.CUSTOMER, "C1"),
        "C2": make_node_id(NodeType.CUSTOMER, "C2"),
        "P1": make_node_id(NodeType.PRODUCT, "P1"),
        "P2": make_node_id(NodeType.PRODUCT, "P2"),
        "O1": make_node_id(NodeType.ORDER, "O1"),
        "O2": make_node_id(NodeType.ORDER, "O2"),
        "SH1": make_node_id(NodeType.SHIPMENT, "SH1"),
    }

    def _node(node_type: NodeType, key: str) -> KGNode:
        return KGNode(id=make_node_id(node_type, key), type=node_type)

    def _edge(edge_type: EdgeType, source: str, target: str) -> KGEdge:
        return KGEdge(
            id=make_edge_id(source, edge_type, target),
            source_id=source,
            target_id=target,
            type=edge_type,
        )

    backend.upsert_node(_node(NodeType.SUPPLIER, "S1"))
    backend.upsert_node(_node(NodeType.SUPPLIER, "S2"))
    backend.upsert_node(_node(NodeType.REGION, "APAC"))
    backend.upsert_node(_node(NodeType.REGION, "NA"))
    backend.upsert_node(_node(NodeType.CUSTOMER, "C1"))
    backend.upsert_node(_node(NodeType.CUSTOMER, "C2"))
    backend.upsert_node(_node(NodeType.PRODUCT, "P1"))
    backend.upsert_node(_node(NodeType.PRODUCT, "P2"))
    backend.upsert_node(_node(NodeType.ORDER, "O1"))
    backend.upsert_node(_node(NodeType.ORDER, "O2"))
    backend.upsert_node(_node(NodeType.SHIPMENT, "SH1"))

    backend.upsert_edge(_edge(EdgeType.LOCATED_IN, ids["S1"], ids["APAC"]))
    backend.upsert_edge(_edge(EdgeType.LOCATED_IN, ids["S2"], ids["NA"]))
    backend.upsert_edge(_edge(EdgeType.DEPENDS_ON, ids["P1"], ids["S1"]))
    backend.upsert_edge(_edge(EdgeType.DEPENDS_ON, ids["P2"], ids["S2"]))
    backend.upsert_edge(_edge(EdgeType.HAS_SUPPLIER, ids["O1"], ids["S1"]))
    backend.upsert_edge(_edge(EdgeType.PLACED_BY, ids["O1"], ids["C1"]))
    backend.upsert_edge(_edge(EdgeType.OF_PRODUCT, ids["O1"], ids["P1"]))
    backend.upsert_edge(_edge(EdgeType.HAS_SUPPLIER, ids["O2"], ids["S1"]))
    backend.upsert_edge(_edge(EdgeType.PLACED_BY, ids["O2"], ids["C2"]))
    backend.upsert_edge(_edge(EdgeType.OF_PRODUCT, ids["O2"], ids["P2"]))
    backend.upsert_edge(_edge(EdgeType.FULFILS_ORDER, ids["SH1"], ids["O1"]))
    backend.upsert_edge(_edge(EdgeType.SUPPLIED_BY, ids["SH1"], ids["S1"]))
    backend.upsert_edge(_edge(EdgeType.SHIPS_TO, ids["SH1"], ids["NA"]))

    return ids


# ---------------------------------------------------------------------------
# Containers
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


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------


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
    """Parametrised backend fixture used by parity tests.

    The ``neo4j`` parameter carries the ``integration`` marker so a
    default ``pytest`` run (which excludes ``-m integration``) only
    exercises the NetworkX variant. ``pytest -m integration`` flips it.
    """
    fixture_name = "networkx_backend" if request.param == "networkx" else "neo4j_backend"
    fixture_value: KGBackend = request.getfixturevalue(fixture_name)
    return fixture_value


@pytest.fixture
def supply_chain(backend: KGBackend) -> dict[str, str]:
    """Build the canonical supply-chain graph on the parametrised backend."""
    return _build_supply_chain(backend)
