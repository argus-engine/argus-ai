# SPDX-License-Identifier: Apache-2.0
"""Parity-test-specific fixtures for the platform-core KG suite.

The KG backend fixtures themselves (``neo4j_container``, ``backend``,
``networkx_backend``, ``neo4j_backend``, …) live in the top-level
:mod:`tests.conftest` because they are shared with the supply-chain KG
test layer. Only the canonical mini supply-chain graph that the parity
tests assert against lives here — it is parity-test scaffolding, not
generic backend infrastructure.

Fixtures provided here:

- ``supply_chain`` (function) — builds the canonical mini supply-chain
  graph on whichever backend the test is parametrised with and returns
  a dict of node-id shortcuts.
"""

from __future__ import annotations

import pytest

from argus.platform_core.kg import (
    EdgeType,
    KGEdge,
    KGNode,
    NodeType,
    make_edge_id,
    make_node_id,
)
from argus.platform_core.kg.base import KGBackend

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


@pytest.fixture
def supply_chain(backend: KGBackend) -> dict[str, str]:
    """Build the canonical supply-chain graph on the parametrised backend."""
    return _build_supply_chain(backend)
