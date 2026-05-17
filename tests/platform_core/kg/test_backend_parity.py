# SPDX-License-Identifier: Apache-2.0
"""Cross-backend parity tests.

The same sequence of upserts and queries should produce equivalent
results on :class:`NetworkXBackend` and :class:`Neo4jBackend`. Both
implementations honour the Protocol contract (merge semantics,
bidirectional BFS for risk / subgraph, directional shortest_path) —
these tests prove they agree on the observable surface.

The ``backend`` fixture is parametrised by
:mod:`tests.platform_core.kg.conftest` over ``["networkx", "neo4j"]``;
the ``neo4j`` variant carries the ``integration`` marker so default
``pytest`` runs only the NetworkX variant and the integration job
runs the Neo4j variant alongside it.

Assertions deliberately target *sets* of reachable nodes, *sets* of
edge types, and counts — not specific path orderings — because the
two backends may pick different spanning-tree edges when multiple
shortest paths exist. The Protocol guarantees set-level parity, not
per-edge identity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from argus.platform_core.kg import (
    EdgeType,
    KGNode,
    NodeType,
    make_node_id,
)

if TYPE_CHECKING:
    from argus.platform_core.kg.base import KGBackend


# ---------------------------------------------------------------------------
# Upsert / get_node parity
# ---------------------------------------------------------------------------


class TestUpsertParity:
    def test_round_trip_preserves_properties_and_refs(self, backend: KGBackend) -> None:
        node = KGNode(
            id="supplier:S1",
            type=NodeType.SUPPLIER,
            properties={"name": "Acme", "country": "GB"},
            source_refs=("dataco:1", "edgar:2"),
        )
        backend.upsert_node(node)

        stored = backend.get_node(node.id)
        assert stored is not None
        assert stored.type is NodeType.SUPPLIER
        assert stored.properties == {"name": "Acme", "country": "GB"}
        assert set(stored.source_refs) == {"dataco:1", "edgar:2"}

    def test_merge_overrides_existing_properties_per_key(self, backend: KGBackend) -> None:
        backend.upsert_node(
            KGNode(
                id="supplier:S1",
                type=NodeType.SUPPLIER,
                properties={"name": "Acme", "country": "GB"},
            )
        )
        backend.upsert_node(
            KGNode(
                id="supplier:S1",
                type=NodeType.SUPPLIER,
                properties={"country": "US", "industry_sic": "3711"},
            )
        )
        stored = backend.get_node("supplier:S1")
        assert stored is not None
        assert stored.properties == {
            "name": "Acme",
            "country": "US",
            "industry_sic": "3711",
        }

    def test_merge_unions_source_refs(self, backend: KGBackend) -> None:
        backend.upsert_node(
            KGNode(
                id="supplier:S1",
                type=NodeType.SUPPLIER,
                source_refs=("dataco:1", "edgar:2"),
            )
        )
        backend.upsert_node(
            KGNode(
                id="supplier:S1",
                type=NodeType.SUPPLIER,
                source_refs=("edgar:2", "gdelt:3"),
            )
        )
        stored = backend.get_node("supplier:S1")
        assert stored is not None
        assert set(stored.source_refs) == {"dataco:1", "edgar:2", "gdelt:3"}

    def test_get_node_returns_none_for_unknown(self, backend: KGBackend) -> None:
        assert backend.get_node("supplier:DOES_NOT_EXIST") is None


# ---------------------------------------------------------------------------
# Neighbors parity
# ---------------------------------------------------------------------------


class TestNeighborsParity:
    def test_incoming_direction_reaches_dependent_orders(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        incoming = backend.neighbors(supply_chain["S1"], direction="in")
        ids = {n.id for n in incoming}
        # Orders, Product, Shipment all point INTO Supplier:S1 via various edges.
        assert ids == {
            supply_chain["O1"],
            supply_chain["O2"],
            supply_chain["P1"],
            supply_chain["SH1"],
        }

    def test_edge_type_filter_restricts_neighbours(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        filtered = backend.neighbors(
            supply_chain["S1"],
            direction="in",
            edge_types=[EdgeType.HAS_SUPPLIER],
        )
        ids = {n.id for n in filtered}
        assert ids == {supply_chain["O1"], supply_chain["O2"]}


# ---------------------------------------------------------------------------
# Cascading risk parity
# ---------------------------------------------------------------------------


class TestCascadingRiskParity:
    def test_bidirectional_bfs_reaches_every_node(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        paths = backend.cascading_risk(supply_chain["S1"], max_hops=3)
        reached = {p.target_id for p in paths}
        assert reached == {
            supply_chain["APAC"],
            supply_chain["NA"],
            supply_chain["O1"],
            supply_chain["O2"],
            supply_chain["C1"],
            supply_chain["C2"],
            supply_chain["P1"],
            supply_chain["P2"],
            supply_chain["SH1"],
            supply_chain["S2"],
        }

    def test_max_hops_bounds_reach(self, backend: KGBackend, supply_chain: dict[str, str]) -> None:
        one_hop = {p.target_id for p in backend.cascading_risk(supply_chain["S1"], max_hops=1)}
        assert one_hop == {
            supply_chain["APAC"],
            supply_chain["O1"],
            supply_chain["O2"],
            supply_chain["P1"],
            supply_chain["SH1"],
        }

    def test_edge_type_filter_restricts_traversal(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        paths = backend.cascading_risk(
            supply_chain["S1"],
            max_hops=3,
            edge_types=[EdgeType.HAS_SUPPLIER],
        )
        reached = {p.target_id for p in paths}
        assert reached == {supply_chain["O1"], supply_chain["O2"]}

    def test_output_sorted_by_hops_then_target_id(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        paths = backend.cascading_risk(supply_chain["S1"], max_hops=3)
        keys = [(p.hops, p.target_id) for p in paths]
        assert keys == sorted(keys)

    def test_unknown_start_returns_empty(self, backend: KGBackend) -> None:
        paths = backend.cascading_risk("supplier:DOES_NOT_EXIST")
        assert list(paths) == []


# ---------------------------------------------------------------------------
# Subgraph parity
# ---------------------------------------------------------------------------


class TestSubgraphParity:
    def test_seed_one_hop_collects_immediate_neighbours(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        sg = backend.subgraph([supply_chain["S1"]], max_hops=1)
        node_ids = {n.id for n in sg.nodes}
        assert node_ids == {
            supply_chain["S1"],
            supply_chain["APAC"],
            supply_chain["O1"],
            supply_chain["O2"],
            supply_chain["P1"],
            supply_chain["SH1"],
        }

    def test_max_hops_zero_returns_only_seeds(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        sg = backend.subgraph([supply_chain["S1"]], max_hops=0)
        node_ids = {n.id for n in sg.nodes}
        assert node_ids == {supply_chain["S1"]}

    def test_missing_seed_silently_skipped(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        sg = backend.subgraph([supply_chain["S1"], "supplier:UNKNOWN"], max_hops=1)
        ids = {n.id for n in sg.nodes}
        assert supply_chain["S1"] in ids
        assert "supplier:UNKNOWN" not in ids

    def test_edge_type_filter_restricts_induced_edges(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        sg = backend.subgraph(
            [supply_chain["S1"]],
            max_hops=2,
            edge_types=[EdgeType.HAS_SUPPLIER],
        )
        assert all(e.type is EdgeType.HAS_SUPPLIER for e in sg.edges)


# ---------------------------------------------------------------------------
# Shortest path parity
# ---------------------------------------------------------------------------


class TestShortestPathParity:
    def test_direct_edge(self, backend: KGBackend, supply_chain: dict[str, str]) -> None:
        path = backend.shortest_path(supply_chain["O1"], supply_chain["S1"])
        assert path is not None
        ids = [n.id for n in path]
        assert ids == [supply_chain["O1"], supply_chain["S1"]]

    def test_no_directed_path_returns_none(self, backend: KGBackend) -> None:
        backend.upsert_node(KGNode(id=make_node_id(NodeType.SUPPLIER, "A"), type=NodeType.SUPPLIER))
        backend.upsert_node(KGNode(id=make_node_id(NodeType.SUPPLIER, "B"), type=NodeType.SUPPLIER))
        assert backend.shortest_path("supplier:A", "supplier:B") is None

    def test_missing_endpoint_returns_none(self, backend: KGBackend) -> None:
        backend.upsert_node(KGNode(id="supplier:A", type=NodeType.SUPPLIER))
        assert backend.shortest_path("supplier:A", "supplier:NOPE") is None


# ---------------------------------------------------------------------------
# Clear parity
# ---------------------------------------------------------------------------


class TestClearParity:
    def test_clear_removes_everything(
        self, backend: KGBackend, supply_chain: dict[str, str]
    ) -> None:
        backend.clear()
        assert backend.get_node(supply_chain["S1"]) is None
        assert list(backend.cascading_risk(supply_chain["S1"])) == []
