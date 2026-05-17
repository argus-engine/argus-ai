# SPDX-License-Identifier: Apache-2.0
"""Contract tests for :class:`NetworkXBackend`.

The cases exercise each Protocol method, the upsert merge semantics
spelled out in :class:`KGBackend`'s docstring, and the bidirectional-BFS
behaviour that makes cascading-risk queries return downstream impacts
even when the underlying foreign-key edges point the other way.
"""

from __future__ import annotations

import pytest

from argus.platform_core.kg import (
    EdgeType,
    KGBackend,
    KGBackendConfig,
    KGEdge,
    KGNode,
    NetworkXBackend,
    NodeType,
    RiskPath,
    make_edge_id,
    make_node_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backend() -> NetworkXBackend:
    return NetworkXBackend(KGBackendConfig(name="nx-test"))


def _node(
    node_type: NodeType,
    key: str,
    *,
    properties: dict[str, object] | None = None,
    source_refs: tuple[str, ...] = (),
) -> KGNode:
    return KGNode(
        id=make_node_id(node_type, key),
        type=node_type,
        properties=properties or {},
        source_refs=source_refs,
    )


def _edge(
    edge_type: EdgeType,
    source: str,
    target: str,
    *,
    properties: dict[str, object] | None = None,
    source_refs: tuple[str, ...] = (),
) -> KGEdge:
    return KGEdge(
        id=make_edge_id(source, edge_type, target),
        source_id=source,
        target_id=target,
        type=edge_type,
        properties=properties or {},
        source_refs=source_refs,
    )


def _build_supply_chain(backend: NetworkXBackend) -> dict[str, str]:
    """Build a small but realistic supply-chain mini-graph.

    Layout (edges shown in their canonical FK orientation)::

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

    Returns a dict of node-id shortcuts keyed by ``"S1"``, ``"P2"`` etc.
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

    backend.upsert_node(_node(NodeType.SUPPLIER, "S1", properties={"name": "Acme"}))
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
# Protocol satisfaction
# ---------------------------------------------------------------------------


class TestProtocolSatisfaction:
    def test_satisfies_kgbackend_protocol(self) -> None:
        assert isinstance(_backend(), KGBackend)

    def test_exposes_config_back_to_caller(self) -> None:
        cfg = KGBackendConfig(name="nx-test")
        backend = NetworkXBackend(cfg)
        assert backend.config is cfg


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_connect_and_disconnect_are_idempotent(self) -> None:
        backend = _backend()
        backend.connect()
        backend.connect()
        backend.disconnect()
        backend.disconnect()
        # No assertion needed beyond not raising — the contract is that
        # repeated calls are safe.

    def test_upsert_works_without_explicit_connect(self) -> None:
        # The in-process backend has no real connection state; upsert
        # before connect() is a supported degenerate case.
        backend = _backend()
        backend.upsert_node(_node(NodeType.SUPPLIER, "S1"))
        assert backend.get_node("supplier:S1") is not None


# ---------------------------------------------------------------------------
# upsert_node
# ---------------------------------------------------------------------------


class TestUpsertNode:
    def test_new_node_is_stored_as_is(self) -> None:
        backend = _backend()
        node = _node(NodeType.SUPPLIER, "S1", properties={"name": "Acme"})
        backend.upsert_node(node)

        assert backend.get_node(node.id) == node

    def test_repeated_upsert_with_same_payload_is_idempotent(self) -> None:
        backend = _backend()
        node = _node(NodeType.SUPPLIER, "S1", properties={"name": "Acme"})
        backend.upsert_node(node)
        backend.upsert_node(node)

        assert backend.get_node(node.id) == node

    def test_merge_overrides_existing_properties_per_key(self) -> None:
        backend = _backend()
        backend.upsert_node(
            _node(
                NodeType.SUPPLIER,
                "S1",
                properties={"name": "Acme", "country": "GB"},
            )
        )
        backend.upsert_node(
            _node(
                NodeType.SUPPLIER,
                "S1",
                properties={"country": "US", "industry_sic": "3711"},
            )
        )

        stored = backend.get_node(make_node_id(NodeType.SUPPLIER, "S1"))
        assert stored is not None
        assert stored.properties == {
            "name": "Acme",  # preserved
            "country": "US",  # overridden
            "industry_sic": "3711",  # added
        }

    def test_merge_unions_source_refs_with_dedup_and_order(self) -> None:
        backend = _backend()
        backend.upsert_node(_node(NodeType.SUPPLIER, "S1", source_refs=("dataco:1", "edgar:2")))
        backend.upsert_node(_node(NodeType.SUPPLIER, "S1", source_refs=("edgar:2", "gdelt:3")))

        stored = backend.get_node(make_node_id(NodeType.SUPPLIER, "S1"))
        assert stored is not None
        assert stored.source_refs == ("dataco:1", "edgar:2", "gdelt:3")

    def test_type_mismatch_raises_value_error(self) -> None:
        backend = _backend()
        node_id = make_node_id(NodeType.SUPPLIER, "S1")
        backend.upsert_node(KGNode(id=node_id, type=NodeType.SUPPLIER))

        with pytest.raises(ValueError, match="already exists with type"):
            backend.upsert_node(KGNode(id=node_id, type=NodeType.CUSTOMER))


# ---------------------------------------------------------------------------
# upsert_edge
# ---------------------------------------------------------------------------


class TestUpsertEdge:
    def test_new_edge_is_stored_with_endpoints_implicit(self) -> None:
        backend = _backend()
        edge = _edge(EdgeType.HAS_SUPPLIER, "order:O1", "supplier:S1")
        backend.upsert_edge(edge)

        # Endpoints were never explicitly upserted; they are dangling.
        assert backend.get_node("order:O1") is None
        assert backend.get_node("supplier:S1") is None
        # But the edge round-trips through neighbours when we later add the nodes.
        backend.upsert_node(_node(NodeType.ORDER, "O1"))
        backend.upsert_node(_node(NodeType.SUPPLIER, "S1"))
        assert backend.neighbors("order:O1") == (_node(NodeType.SUPPLIER, "S1"),)

    def test_merge_overrides_properties_per_key(self) -> None:
        backend = _backend()
        edge_id = make_edge_id("a", EdgeType.AFFECTS, "b")
        backend.upsert_edge(
            KGEdge(
                id=edge_id,
                source_id="a",
                target_id="b",
                type=EdgeType.AFFECTS,
                properties={"weight": 0.3, "channel": "news"},
            )
        )
        backend.upsert_edge(
            KGEdge(
                id=edge_id,
                source_id="a",
                target_id="b",
                type=EdgeType.AFFECTS,
                properties={"weight": 0.9, "confidence": 0.7},
            )
        )

        # Walk the graph to re-read the merged edge.
        backend.upsert_node(KGNode(id="a", type=NodeType.EVENT_SIGNAL))
        backend.upsert_node(KGNode(id="b", type=NodeType.SUPPLIER))
        result = backend.subgraph(["a"], max_hops=1)
        assert len(result.edges) == 1
        merged = result.edges[0]
        assert merged.properties == {
            "channel": "news",  # preserved
            "weight": 0.9,  # overridden
            "confidence": 0.7,  # added
        }

    def test_merge_unions_source_refs_with_dedup(self) -> None:
        backend = _backend()
        edge_id = make_edge_id("a", EdgeType.AFFECTS, "b")
        backend.upsert_edge(
            KGEdge(
                id=edge_id,
                source_id="a",
                target_id="b",
                type=EdgeType.AFFECTS,
                source_refs=("gdelt:1",),
            )
        )
        backend.upsert_edge(
            KGEdge(
                id=edge_id,
                source_id="a",
                target_id="b",
                type=EdgeType.AFFECTS,
                source_refs=("gdelt:1", "edgar:2"),
            )
        )

        backend.upsert_node(KGNode(id="a", type=NodeType.EVENT_SIGNAL))
        backend.upsert_node(KGNode(id="b", type=NodeType.SUPPLIER))
        result = backend.subgraph(["a"], max_hops=1)
        assert result.edges[0].source_refs == ("gdelt:1", "edgar:2")

    def test_type_mismatch_raises_value_error(self) -> None:
        backend = _backend()
        # Construct two edges that share an ID but disagree on type — bypassing
        # make_edge_id, which would naturally produce different IDs.
        shared_id = "manual-edge-id"
        backend.upsert_edge(
            KGEdge(
                id=shared_id,
                source_id="x",
                target_id="y",
                type=EdgeType.AFFECTS,
            )
        )

        with pytest.raises(ValueError, match="already exists with type"):
            backend.upsert_edge(
                KGEdge(
                    id=shared_id,
                    source_id="x",
                    target_id="y",
                    type=EdgeType.MENTIONS,
                )
            )

    def test_multi_edge_between_same_pair_is_preserved(self) -> None:
        backend = _backend()
        backend.upsert_node(_node(NodeType.SHIPMENT, "SH1"))
        backend.upsert_node(_node(NodeType.REGION, "NA"))
        # Two different relationship types between the same pair.
        backend.upsert_edge(_edge(EdgeType.SHIPS_TO, "shipment:SH1", "region:NA"))
        backend.upsert_edge(_edge(EdgeType.LOCATED_IN, "shipment:SH1", "region:NA"))

        sg = backend.subgraph(["shipment:SH1"], max_hops=1)
        edge_types = sorted(e.type.value for e in sg.edges)
        assert edge_types == ["LOCATED_IN", "SHIPS_TO"]


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


class TestGetNode:
    def test_returns_node_after_upsert(self) -> None:
        backend = _backend()
        node = _node(NodeType.REGION, "APAC")
        backend.upsert_node(node)
        assert backend.get_node(node.id) == node

    def test_returns_none_for_unknown_id(self) -> None:
        assert _backend().get_node("supplier:NOPE") is None

    def test_returns_none_for_dangling_endpoint(self) -> None:
        backend = _backend()
        # Edge implicitly creates the endpoint without a KGNode payload.
        backend.upsert_edge(_edge(EdgeType.AFFECTS, "event_signal:E1", "supplier:S9"))
        assert backend.get_node("supplier:S9") is None


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------


class TestNeighbors:
    def test_outgoing_default(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        out = backend.neighbors(ids["S1"])
        # Supplier:S1's only outgoing edge is LOCATED_IN -> Region:APAC.
        assert [n.id for n in out] == [ids["APAC"]]

    def test_incoming_direction_finds_dependents(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        incoming = backend.neighbors(ids["S1"], direction="in")
        # Orders point to Supplier:S1; Product:P1 -DEPENDS_ON-> Supplier:S1;
        # Shipment:SH1 -SUPPLIED_BY-> Supplier:S1.
        assert sorted(n.id for n in incoming) == sorted(
            [ids["O1"], ids["O2"], ids["P1"], ids["SH1"]]
        )

    def test_both_direction_unions_in_and_out(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        both = backend.neighbors(ids["S1"], direction="both")
        assert sorted(n.id for n in both) == sorted(
            [ids["APAC"], ids["O1"], ids["O2"], ids["P1"], ids["SH1"]]
        )

    def test_edge_types_filter_restricts_traversal(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        filtered = backend.neighbors(ids["S1"], direction="in", edge_types=[EdgeType.HAS_SUPPLIER])
        assert sorted(n.id for n in filtered) == sorted([ids["O1"], ids["O2"]])

    def test_unknown_node_returns_empty(self) -> None:
        assert _backend().neighbors("supplier:nope") == ()

    def test_skips_dangling_neighbours(self) -> None:
        backend = _backend()
        backend.upsert_node(_node(NodeType.EVENT_SIGNAL, "E1"))
        backend.upsert_edge(_edge(EdgeType.MENTIONS, "event_signal:E1", "supplier:UNKNOWN"))
        # Target is dangling — neighbors must filter it out.
        assert backend.neighbors("event_signal:E1") == ()


# ---------------------------------------------------------------------------
# subgraph
# ---------------------------------------------------------------------------


class TestSubgraph:
    def test_single_seed_one_hop(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        sg = backend.subgraph([ids["S1"]], max_hops=1)
        seen = {n.id for n in sg.nodes}
        assert seen == {ids["S1"], ids["APAC"], ids["O1"], ids["O2"], ids["P1"], ids["SH1"]}

    def test_multi_seed_dedupes_overlap(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        sg = backend.subgraph([ids["O1"], ids["O2"]], max_hops=1)
        # Both orders share Supplier:S1 — should appear exactly once.
        supplier_count = sum(1 for n in sg.nodes if n.id == ids["S1"])
        assert supplier_count == 1

    def test_max_hops_zero_returns_only_seeds(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        sg = backend.subgraph([ids["S1"]], max_hops=0)
        assert [n.id for n in sg.nodes] == [ids["S1"]]
        assert sg.edges == ()

    def test_edge_types_filter_constrains_induced_edges(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        sg = backend.subgraph([ids["S1"]], max_hops=2, edge_types=[EdgeType.HAS_SUPPLIER])
        # Only HAS_SUPPLIER edges connect collected nodes; no other types
        # leak into the result.
        assert all(e.type is EdgeType.HAS_SUPPLIER for e in sg.edges)

    def test_missing_seed_silently_skipped(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        sg = backend.subgraph([ids["S1"], "supplier:DOES_NOT_EXIST"], max_hops=1)
        assert ids["S1"] in {n.id for n in sg.nodes}
        assert "supplier:DOES_NOT_EXIST" not in {n.id for n in sg.nodes}

    def test_returns_induced_edges_not_just_path_edges(self) -> None:
        # Subgraph induction means an edge between any two collected
        # nodes is included, even if BFS didn't traverse it as part of
        # the spanning tree.
        backend = _backend()
        ids = _build_supply_chain(backend)
        sg = backend.subgraph([ids["S1"]], max_hops=2)
        edge_ids = {e.id for e in sg.edges}
        # The Order:O1 -OF_PRODUCT-> Product:P1 edge connects two
        # already-collected nodes and must appear.
        assert make_edge_id(ids["O1"], EdgeType.OF_PRODUCT, ids["P1"]) in edge_ids


# ---------------------------------------------------------------------------
# cascading_risk
# ---------------------------------------------------------------------------


class TestCascadingRisk:
    def test_bidirectional_bfs_from_supplier(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        paths = backend.cascading_risk(ids["S1"], max_hops=3)
        reached = {p.target_id for p in paths}
        # Every other node in the graph is reachable within 3 hops.
        assert reached == {
            ids["APAC"],
            ids["NA"],
            ids["O1"],
            ids["O2"],
            ids["C1"],
            ids["C2"],
            ids["P1"],
            ids["P2"],
            ids["SH1"],
            ids["S2"],
        }

    def test_max_hops_bounds_reach(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        one_hop = {p.target_id for p in backend.cascading_risk(ids["S1"], max_hops=1)}
        # Hop 1 from Supplier:S1: APAC, O1, O2, P1, SH1.
        assert one_hop == {ids["APAC"], ids["O1"], ids["O2"], ids["P1"], ids["SH1"]}

    def test_edge_types_filter_restricts_traversal(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        paths = backend.cascading_risk(ids["S1"], max_hops=3, edge_types=[EdgeType.HAS_SUPPLIER])
        # Only Orders are reachable via HAS_SUPPLIER; no further hops.
        reached = {p.target_id for p in paths}
        assert reached == {ids["O1"], ids["O2"]}

    def test_output_sorted_by_hops_then_target_id(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        paths = backend.cascading_risk(ids["S1"], max_hops=3)
        keys = [(p.hops, p.target_id) for p in paths]
        assert keys == sorted(keys)

    def test_unknown_start_returns_empty(self) -> None:
        assert _backend().cascading_risk("supplier:NOPE") == []

    def test_each_path_starts_at_start_id(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        for path in backend.cascading_risk(ids["S1"], max_hops=2):
            assert path.start_id == ids["S1"]
            assert path.hops == len(path.path)

    def test_returned_paths_are_riskpath_instances(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        paths = backend.cascading_risk(ids["S1"], max_hops=1)
        assert paths
        assert all(isinstance(p, RiskPath) for p in paths)


# ---------------------------------------------------------------------------
# shortest_path
# ---------------------------------------------------------------------------


class TestShortestPath:
    def test_direct_edge(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        # Order:O1 -HAS_SUPPLIER-> Supplier:S1 is a direct edge.
        path = backend.shortest_path(ids["O1"], ids["S1"])
        assert path is not None
        assert [n.id for n in path] == [ids["O1"], ids["S1"]]

    def test_returns_none_when_source_missing(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        assert backend.shortest_path("supplier:NOPE", ids["S1"]) is None

    def test_returns_none_when_target_missing(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)
        assert backend.shortest_path(ids["S1"], "supplier:NOPE") is None

    def test_returns_none_when_no_directed_path(self) -> None:
        backend = _backend()
        backend.upsert_node(_node(NodeType.SUPPLIER, "S1"))
        backend.upsert_node(_node(NodeType.SUPPLIER, "S2"))
        # No edge between them at all.
        assert backend.shortest_path("supplier:S1", "supplier:S2") is None

    def test_returns_none_for_dangling_intermediate(self) -> None:
        backend = _backend()
        # E1 -AFFECTS-> SUP:UNKNOWN (dangling) -AFFECTS-> S2
        backend.upsert_node(_node(NodeType.EVENT_SIGNAL, "E1"))
        backend.upsert_node(_node(NodeType.SUPPLIER, "S2"))
        backend.upsert_edge(_edge(EdgeType.AFFECTS, "event_signal:E1", "supplier:UNKNOWN"))
        backend.upsert_edge(_edge(EdgeType.AFFECTS, "supplier:UNKNOWN", "supplier:S2"))
        # nx.shortest_path returns a path through the dangling endpoint —
        # the backend must refuse to materialise it.
        result = backend.shortest_path("event_signal:E1", "supplier:S2")
        assert result is None


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_removes_every_node_and_edge(self) -> None:
        backend = _backend()
        ids = _build_supply_chain(backend)

        backend.clear()

        assert backend.get_node(ids["S1"]) is None
        assert backend.cascading_risk(ids["S1"]) == []
        assert backend.subgraph([ids["S1"]]).nodes == ()


# ---------------------------------------------------------------------------
# Self-loops
# ---------------------------------------------------------------------------


class TestSelfLoop:
    def test_self_loop_edge_is_stored_and_returned(self) -> None:
        backend = _backend()
        backend.upsert_node(_node(NodeType.SUPPLIER, "S1"))
        # Pathological but representable — supplier depends on itself.
        backend.upsert_edge(_edge(EdgeType.DEPENDS_ON, "supplier:S1", "supplier:S1"))

        sg = backend.subgraph(["supplier:S1"], max_hops=1)
        assert len(sg.edges) == 1
        assert sg.edges[0].source_id == sg.edges[0].target_id == "supplier:S1"
