# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the KG builder and adapter Protocol.

A minimal dict-backed stub backend stands in for the real
implementations (which land in Tasks #2 and #3). The stub satisfies the
:class:`KGBackend` Protocol via duck typing — confirming the Protocol's
``runtime_checkable`` ``isinstance`` check also exercises that contract.

What these tests verify:

- The builder upserts nodes before edges per entity.
- Repeated ingest of the same entity is idempotent at the backend.
- The entity iterable is consumed lazily (a one-shot generator works).
- :class:`IngestionReport` carries accurate counts and a tz-aware start.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from argus.platform_core.kg.base import (
    Direction,
    KGBackend,
    RiskPath,
    Subgraph,
)
from argus.platform_core.kg.builder import KGAdapter, KGBuilder
from argus.platform_core.kg.schema import (
    EdgeType,
    KGEdge,
    KGNode,
    NodeType,
    make_edge_id,
    make_node_id,
)

# ---------------------------------------------------------------------------
# Stub backend — dict-backed, satisfies the KGBackend Protocol
# ---------------------------------------------------------------------------


class _StubBackend:
    """Minimal in-memory KGBackend. Records the order of upsert calls.

    Implements just enough of the Protocol to support the builder tests.
    Query methods return empty results — exercising them is the job of
    the real backends in Tasks #2 and #3.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, KGNode] = {}
        self.edges: dict[str, KGEdge] = {}
        self.call_order: list[tuple[str, str]] = []
        self.connect_calls = 0
        self.disconnect_calls = 0

    def connect(self) -> None:
        self.connect_calls += 1

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def upsert_node(self, node: KGNode) -> None:
        self.nodes[node.id] = node
        self.call_order.append(("node", node.id))

    def upsert_edge(self, edge: KGEdge) -> None:
        self.edges[edge.id] = edge
        self.call_order.append(("edge", edge.id))

    def get_node(self, node_id: str) -> KGNode | None:
        return self.nodes.get(node_id)

    def neighbors(
        self,
        node_id: str,  # noqa: ARG002
        *,
        edge_types: Iterable[EdgeType] | None = None,  # noqa: ARG002
        direction: Direction = "out",  # noqa: ARG002
    ) -> Sequence[KGNode]:
        return ()

    def subgraph(
        self,
        seed_ids: Iterable[str],  # noqa: ARG002
        *,
        max_hops: int = 1,  # noqa: ARG002
        edge_types: Iterable[EdgeType] | None = None,  # noqa: ARG002
    ) -> Subgraph:
        return Subgraph()

    def cascading_risk(
        self,
        start_id: str,  # noqa: ARG002
        *,
        max_hops: int = 3,  # noqa: ARG002
        edge_types: Iterable[EdgeType] | None = None,  # noqa: ARG002
    ) -> Sequence[RiskPath]:
        return ()

    def shortest_path(
        self,
        source_id: str,  # noqa: ARG002
        target_id: str,  # noqa: ARG002
    ) -> Sequence[KGNode] | None:
        return None

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.call_order.clear()


# ---------------------------------------------------------------------------
# Entity + adapter test doubles
# ---------------------------------------------------------------------------


class _FakeEntity:
    """Tiny stand-in for a domain entity, used only in these tests."""

    def __init__(self, supplier_key: str, order_key: str) -> None:
        self.supplier_key = supplier_key
        self.order_key = order_key


class _FakeAdapter:
    """Maps :class:`_FakeEntity` to one Supplier node, one Order node, one edge.

    Satisfies the :class:`KGAdapter` Protocol via duck typing.
    """

    def to_nodes(self, entity: _FakeEntity) -> Iterable[KGNode]:
        yield KGNode(
            id=make_node_id(NodeType.SUPPLIER, entity.supplier_key),
            type=NodeType.SUPPLIER,
        )
        yield KGNode(
            id=make_node_id(NodeType.ORDER, entity.order_key),
            type=NodeType.ORDER,
        )

    def to_edges(self, entity: _FakeEntity) -> Iterable[KGEdge]:
        source = make_node_id(NodeType.ORDER, entity.order_key)
        target = make_node_id(NodeType.SUPPLIER, entity.supplier_key)
        yield KGEdge(
            id=make_edge_id(source, EdgeType.HAS_SUPPLIER, target),
            source_id=source,
            target_id=target,
            type=EdgeType.HAS_SUPPLIER,
        )


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------


class TestProtocolSatisfaction:
    def test_stub_backend_satisfies_kgbackend_protocol(self) -> None:
        assert isinstance(_StubBackend(), KGBackend)

    def test_fake_adapter_satisfies_kgadapter_protocol(self) -> None:
        assert isinstance(_FakeAdapter(), KGAdapter)


# ---------------------------------------------------------------------------
# KGBuilder.ingest behaviour
# ---------------------------------------------------------------------------


class TestKGBuilderIngest:
    def test_ingests_nodes_and_edges_from_one_entity(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        report = builder.ingest([_FakeEntity("SUP-1", "ORD-1")])

        assert set(backend.nodes) == {"supplier:SUP-1", "order:ORD-1"}
        assert set(backend.edges) == {
            "order:ORD-1-HAS_SUPPLIER->supplier:SUP-1",
        }
        assert report.nodes_seen == 2
        assert report.edges_seen == 1

    def test_nodes_are_upserted_before_edges_per_entity(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        builder.ingest([_FakeEntity("SUP-1", "ORD-1")])

        kinds = [kind for kind, _ in backend.call_order]
        first_edge_idx = kinds.index("edge")
        # Every node call must precede the first edge call.
        assert all(k == "node" for k in kinds[:first_edge_idx])

    def test_repeated_ingest_of_same_entity_is_idempotent(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())
        entity = _FakeEntity("SUP-1", "ORD-1")

        builder.ingest([entity])
        builder.ingest([entity])

        # Backend dedupes by id — sets identical after second ingest.
        assert set(backend.nodes) == {"supplier:SUP-1", "order:ORD-1"}
        assert set(backend.edges) == {
            "order:ORD-1-HAS_SUPPLIER->supplier:SUP-1",
        }

    def test_consumes_iterable_lazily(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        consumed: list[_FakeEntity] = []

        def one_shot() -> Iterator[_FakeEntity]:
            for i in range(3):
                entity = _FakeEntity(f"SUP-{i}", f"ORD-{i}")
                consumed.append(entity)
                yield entity

        report = builder.ingest(one_shot())

        assert len(consumed) == 3
        assert report.nodes_seen == 6
        assert report.edges_seen == 3

    def test_empty_iterable_yields_zero_report(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        report = builder.ingest([])

        assert report.nodes_seen == 0
        assert report.edges_seen == 0
        assert backend.nodes == {}
        assert backend.edges == {}

    def test_ingest_does_not_open_or_close_backend_connection(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        builder.ingest([_FakeEntity("SUP-1", "ORD-1")])

        # Lifecycle is the caller's responsibility — the builder must not
        # silently connect or disconnect on its own.
        assert backend.connect_calls == 0
        assert backend.disconnect_calls == 0


# ---------------------------------------------------------------------------
# IngestionReport
# ---------------------------------------------------------------------------


class TestIngestionReport:
    def test_started_at_is_tz_aware_utc(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        before = datetime.now(UTC)
        report = builder.ingest([_FakeEntity("SUP-1", "ORD-1")])
        after = datetime.now(UTC)

        assert report.started_at.tzinfo is not None
        assert before <= report.started_at <= after

    def test_duration_ms_is_non_negative(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())

        report = builder.ingest([_FakeEntity("SUP-1", "ORD-1")])

        assert report.duration_ms >= 0

    def test_report_is_frozen(self) -> None:
        backend = _StubBackend()
        builder = KGBuilder(backend, _FakeAdapter())
        report = builder.ingest([_FakeEntity("SUP-1", "ORD-1")])

        with pytest.raises(ValidationError):
            report.nodes_seen = 999


# ---------------------------------------------------------------------------
# Subgraph + RiskPath wrappers
# ---------------------------------------------------------------------------


class TestResultWrappers:
    def test_empty_subgraph_is_falsy_and_zero_length(self) -> None:
        sg = Subgraph()
        assert len(sg) == 0
        assert bool(sg) is False

    def test_populated_subgraph_reports_node_count(self) -> None:
        node = KGNode(id="supplier:X", type=NodeType.SUPPLIER)
        sg = Subgraph(nodes=(node,))
        assert len(sg) == 1
        assert bool(sg) is True

    def test_risk_path_requires_at_least_one_hop(self) -> None:
        with pytest.raises(ValidationError):
            RiskPath(start_id="a", target_id="b", path=(), hops=0)
