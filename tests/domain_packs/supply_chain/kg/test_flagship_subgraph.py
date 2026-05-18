# SPDX-License-Identifier: Apache-2.0
"""Flagship subgraph-extraction test against the deterministic fixture topology.

Parametrised over both backends via the shared ``backend`` fixture in
:mod:`tests.conftest`. The neo4j parameter carries the ``integration``
marker, so a default ``pytest`` run exercises the NetworkX backend
only; ``pytest -m integration`` flips it.

The fixture topology was designed by hand. The assertions reference
``EXPECTED_SUBGRAPH_NODE_IDS_FROM_SUP_A_MAX_HOPS_1`` and
``EXPECTED_SUBGRAPH_EDGE_KEYS_FROM_SUP_A_MAX_HOPS_1`` from
:mod:`tests.domain_packs.supply_chain.kg.fixtures` — see that module's
docstring for the induced-edge derivation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from argus.domain_packs.supply_chain.kg_adapter import SupplyChainKGAdapter
from argus.platform_core.kg.builder import KGBuilder
from tests.domain_packs.supply_chain.kg.fixtures import (
    EXPECTED_SUBGRAPH_EDGE_KEYS_FROM_SUP_A_MAX_HOPS_1,
    EXPECTED_SUBGRAPH_NODE_IDS_FROM_SUP_A_MAX_HOPS_1,
    build_entity_stream,
)

if TYPE_CHECKING:
    from argus.platform_core.kg.base import KGBackend


def _ingest_canonical(backend: KGBackend) -> None:
    """Drive the canonical entity stream through the adapter onto ``backend``."""
    adapter = SupplyChainKGAdapter()
    builder = KGBuilder(backend, adapter)
    builder.ingest(build_entity_stream())


class TestSubgraphExtractionFromSupA:
    def test_returns_exact_node_set(self, backend: KGBackend) -> None:
        _ingest_canonical(backend)

        result = backend.subgraph(["supplier:SUP-A"], max_hops=1)

        node_ids = frozenset(n.id for n in result.nodes)
        assert node_ids == EXPECTED_SUBGRAPH_NODE_IDS_FROM_SUP_A_MAX_HOPS_1

    def test_returns_exact_induced_edge_set(self, backend: KGBackend) -> None:
        # The induced-edge contract: every edge between two collected
        # nodes is returned, not just the spanning-tree edges traversed
        # during BFS. So order:O1 -SHIPS_TO-> region:EMEA is included
        # even though BFS first reaches EMEA via SUP-A -LOCATED_IN-> EMEA.
        _ingest_canonical(backend)

        result = backend.subgraph(["supplier:SUP-A"], max_hops=1)

        edge_keys = frozenset((e.source_id, e.type.value, e.target_id) for e in result.edges)
        assert edge_keys == EXPECTED_SUBGRAPH_EDGE_KEYS_FROM_SUP_A_MAX_HOPS_1

    def test_subgraph_excludes_nodes_beyond_one_hop(self, backend: KGBackend) -> None:
        # Products and customers (hop 2 from SUP-A) and SUP-B side
        # (hop 3+) must not appear in the max_hops=1 result.
        _ingest_canonical(backend)

        result = backend.subgraph(["supplier:SUP-A"], max_hops=1)

        node_ids = frozenset(n.id for n in result.nodes)
        for excluded in (
            "product:P1",
            "product:P2",
            "customer:CUST-1",
            "customer:CUST-2",
            "customer:CUST-3",
            "region:NA",
            "supplier:SUP-B",
        ):
            assert excluded not in node_ids

    def test_missing_seed_silently_skipped(self, backend: KGBackend) -> None:
        # Documented contract on :meth:`KGBackend.subgraph`: seeds that
        # do not exist are silently skipped, the returned subgraph
        # reflects what was found. Pin on a real, populated backend.
        _ingest_canonical(backend)

        result = backend.subgraph(["supplier:SUP-A", "supplier:DOES-NOT-EXIST"], max_hops=1)

        node_ids = frozenset(n.id for n in result.nodes)
        assert node_ids == EXPECTED_SUBGRAPH_NODE_IDS_FROM_SUP_A_MAX_HOPS_1

    def test_subgraph_results_are_sorted_by_id(self, backend: KGBackend) -> None:
        # The implementations of both backends sort their result tuples
        # by id for determinism. Pin so a regression in either surfaces here.
        _ingest_canonical(backend)

        result = backend.subgraph(["supplier:SUP-A"], max_hops=1)

        node_ids_in_order = [n.id for n in result.nodes]
        edge_ids_in_order = [e.id for e in result.edges]
        assert node_ids_in_order == sorted(node_ids_in_order)
        assert edge_ids_in_order == sorted(edge_ids_in_order)
