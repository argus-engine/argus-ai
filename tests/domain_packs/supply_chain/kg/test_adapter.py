# SPDX-License-Identifier: Apache-2.0
"""Unit tests for :class:`SupplyChainKGAdapter`.

Covers, in order:

- Protocol satisfaction (the adapter conforms to :class:`KGAdapter`).
- Per-entity mapping correctness for each of the four supply-chain types.
- The four-rule entity resolution for ``EventSignal.entities_mentioned``,
  including priority order and the unresolved-counter behaviour.
- The caller-side ordering contract: an :class:`EventSignal` ingested
  before the entities it mentions yields silent unresolved hits, which
  is the documented (and now test-pinned) consequence.
- Deterministic, idempotent output: repeated calls with the same input
  return equal sequences so the builder's repeat-ingest contract holds.
- The type guard rejecting non-supply-chain entities.

These are pure unit tests — no backend is involved. The flagship tests
in the sibling files exercise the adapter against both backends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from argus.domain_packs.supply_chain.data.schemas import (
    EventCategory,
    EventSeverity,
    EventSignal,
    Order,
    OrderStatus,
    Region,
    Shipment,
    ShipmentStatus,
    ShippingMode,
    Supplier,
)
from argus.domain_packs.supply_chain.kg_adapter import SupplyChainKGAdapter
from argus.platform_core.kg.builder import KGAdapter
from argus.platform_core.kg.schema import EdgeType, KGEdge, KGNode, NodeType

# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------


def _make_supplier(
    supplier_id: str = "SUP-A",
    *,
    region: Region = Region.EMEA,
    country: str = "GB",
    tier: int = 1,
    industry_sic: str | None = None,
    ticker: str | None = None,
    cik: str | None = None,
) -> Supplier:
    return Supplier(
        supplier_id=supplier_id,
        name=f"{supplier_id} Trading Ltd",
        country=country,
        region=region,
        tier=tier,
        industry_sic=industry_sic,
        ticker=ticker,
        cik=cik,
    )


def _make_order(
    order_id: str = "O1",
    *,
    customer_id: str = "CUST-1",
    product_id: str = "P1",
    supplier_id: str | None = "SUP-A",
    destination_region: Region = Region.EMEA,
    status: OrderStatus = OrderStatus.CONFIRMED,
) -> Order:
    return Order(
        order_id=order_id,
        customer_id=customer_id,
        product_id=product_id,
        quantity=3,
        unit_price=Decimal("12.50"),
        currency="USD",
        placed_at=datetime(2026, 1, 15, 9, 0, tzinfo=UTC),
        status=status,
        destination_region=destination_region,
        supplier_id=supplier_id,
    )


def _make_shipment(
    shipment_id: str = "SH-O1",
    *,
    order_id: str = "O1",
    supplier_id: str = "SUP-A",
    status: ShipmentStatus = ShipmentStatus.IN_TRANSIT,
) -> Shipment:
    return Shipment(
        shipment_id=shipment_id,
        order_id=order_id,
        supplier_id=supplier_id,
        origin_location="GBLON",
        destination_location="DEHAM",
        shipping_mode=ShippingMode.SEA,
        scheduled_departure=datetime(2026, 1, 16, 8, 0, tzinfo=UTC),
        scheduled_arrival=datetime(2026, 1, 25, 18, 0, tzinfo=UTC),
        status=status,
        units=120,
    )


def _make_event(
    event_id: str = "E1",
    *,
    entities_mentioned: list[str] | None = None,
    category: EventCategory = EventCategory.DISRUPTION,
    severity: EventSeverity = EventSeverity.HIGH,
) -> EventSignal:
    return EventSignal(
        event_id=event_id,
        occurred_at=datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
        category=category,
        severity=severity,
        source_name="TestFeed",
        title="Test event",
        summary="Test summary",
        entities_mentioned=entities_mentioned or [],
    )


def _node_ids(nodes: list[KGNode]) -> set[str]:
    return {n.id for n in nodes}


def _edge_keys(edges: list[KGEdge]) -> set[tuple[str, str, str]]:
    return {(e.source_id, e.type.value, e.target_id) for e in edges}


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------


class TestProtocolSatisfaction:
    def test_adapter_satisfies_kgadapter_protocol(self) -> None:
        assert isinstance(SupplyChainKGAdapter(), KGAdapter)

    def test_counters_default_to_zero_unresolved(self) -> None:
        adapter = SupplyChainKGAdapter()
        assert dict(adapter.counters()) == {"unresolved_mentions": 0}


# ---------------------------------------------------------------------------
# Supplier mapping
# ---------------------------------------------------------------------------


class TestSupplierMapping:
    def test_emits_supplier_and_region_nodes(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_supplier(region=Region.APAC)))

        assert _node_ids(nodes) == {"supplier:SUP-A", "region:APAC"}

    def test_supplier_node_carries_scalar_properties(self) -> None:
        adapter = SupplyChainKGAdapter()
        supplier = _make_supplier(
            country="DE",
            tier=2,
            industry_sic="3711",
            ticker="ACME",
            cik="0001234567",
        )
        nodes = list(adapter.to_nodes(supplier))

        supplier_node = next(n for n in nodes if n.type is NodeType.SUPPLIER)
        assert supplier_node.properties == {
            "name": "SUP-A Trading Ltd",
            "country": "DE",
            "tier": 2,
            "industry_sic": "3711",
            "ticker": "ACME",
            "cik": "0001234567",
        }

    def test_supplier_node_omits_unset_optional_properties(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_supplier()))

        supplier_node = next(n for n in nodes if n.type is NodeType.SUPPLIER)
        # The three optional fields default to None; the adapter elides
        # them rather than storing None values that complicate downstream
        # property checks.
        assert "industry_sic" not in supplier_node.properties
        assert "ticker" not in supplier_node.properties
        assert "cik" not in supplier_node.properties

    def test_emits_located_in_edge(self) -> None:
        adapter = SupplyChainKGAdapter()
        edges = list(adapter.to_edges(_make_supplier(region=Region.NA)))

        assert _edge_keys(edges) == {
            ("supplier:SUP-A", "LOCATED_IN", "region:NA"),
        }


# ---------------------------------------------------------------------------
# Order mapping
# ---------------------------------------------------------------------------


class TestOrderMapping:
    def test_emits_order_product_customer_and_region_nodes(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_order()))

        assert _node_ids(nodes) == {
            "order:O1",
            "product:P1",
            "customer:CUST-1",
            "region:EMEA",
        }

    def test_order_properties_serialise_decimal_as_str_and_status_as_value(self) -> None:
        adapter = SupplyChainKGAdapter()
        order = _make_order(status=OrderStatus.SHIPPED)
        nodes = list(adapter.to_nodes(order))

        order_node = next(n for n in nodes if n.type is NodeType.ORDER)
        assert order_node.properties["unit_price"] == "12.50"
        assert order_node.properties["status"] == "shipped"
        assert order_node.properties["quantity"] == 3
        assert order_node.properties["currency"] == "USD"

    def test_emits_four_edges_when_supplier_is_known(self) -> None:
        adapter = SupplyChainKGAdapter()
        edges = list(adapter.to_edges(_make_order()))

        assert _edge_keys(edges) == {
            ("order:O1", "OF_PRODUCT", "product:P1"),
            ("order:O1", "PLACED_BY", "customer:CUST-1"),
            ("order:O1", "SHIPS_TO", "region:EMEA"),
            ("order:O1", "HAS_SUPPLIER", "supplier:SUP-A"),
        }

    def test_omits_has_supplier_edge_when_order_supplier_id_is_none(self) -> None:
        adapter = SupplyChainKGAdapter()
        edges = list(adapter.to_edges(_make_order(supplier_id=None)))

        assert _edge_keys(edges) == {
            ("order:O1", "OF_PRODUCT", "product:P1"),
            ("order:O1", "PLACED_BY", "customer:CUST-1"),
            ("order:O1", "SHIPS_TO", "region:EMEA"),
        }

    def test_order_does_not_emit_a_shipment_ships_to(self) -> None:
        # Documents the asymmetry: only Order.destination_region -> SHIPS_TO,
        # because Shipment.destination_location is a free-form locode/string.
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_shipment()))
        edges = list(adapter.to_edges(_make_shipment()))

        assert all(n.type is not NodeType.REGION for n in nodes)
        assert all(e.type is not EdgeType.SHIPS_TO for e in edges)


# ---------------------------------------------------------------------------
# Shipment mapping
# ---------------------------------------------------------------------------


class TestShipmentMapping:
    def test_emits_only_shipment_node(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_shipment()))

        assert _node_ids(nodes) == {"shipment:SH-O1"}

    def test_emits_fulfils_order_and_supplied_by_edges(self) -> None:
        adapter = SupplyChainKGAdapter()
        edges = list(adapter.to_edges(_make_shipment()))

        assert _edge_keys(edges) == {
            ("shipment:SH-O1", "FULFILS_ORDER", "order:O1"),
            ("shipment:SH-O1", "SUPPLIED_BY", "supplier:SUP-A"),
        }

    def test_shipment_carries_scalar_properties_including_enums_as_values(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_shipment(status=ShipmentStatus.DELAYED)))

        shipment = next(iter(nodes))
        assert shipment.properties["shipping_mode"] == "sea"
        assert shipment.properties["status"] == "delayed"
        assert shipment.properties["units"] == 120
        assert shipment.properties["origin_location"] == "GBLON"

    def test_actual_timestamps_elided_when_unset(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_shipment()))

        shipment = next(iter(nodes))
        assert "actual_departure" not in shipment.properties
        assert "actual_arrival" not in shipment.properties


# ---------------------------------------------------------------------------
# EventSignal mapping + resolution
# ---------------------------------------------------------------------------


class TestEventSignalResolution:
    def test_emits_event_node(self) -> None:
        adapter = SupplyChainKGAdapter()
        nodes = list(adapter.to_nodes(_make_event()))

        assert _node_ids(nodes) == {"event_signal:E1"}

    def test_resolves_against_seen_supplier(self) -> None:
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_supplier("SUP-A")))
        event = _make_event(entities_mentioned=["SUP-A"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "supplier:SUP-A"),
        }

    def test_resolves_against_region_enum_value(self) -> None:
        adapter = SupplyChainKGAdapter()
        event = _make_event(entities_mentioned=["APAC"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "region:APAC"),
        }

    def test_resolves_against_seen_product_via_order(self) -> None:
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_order(product_id="WIDGET-9")))
        event = _make_event(entities_mentioned=["WIDGET-9"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "product:WIDGET-9"),
        }

    def test_resolves_against_seen_customer_via_order(self) -> None:
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_order(customer_id="CUST-Z")))
        event = _make_event(entities_mentioned=["CUST-Z"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "customer:CUST-Z"),
        }

    def test_priority_order_supplier_beats_region(self) -> None:
        # Edge case: a supplier id that happens to equal a Region value.
        # Rule 1 (supplier) wins over rule 2 (region).
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_supplier("NA")))
        event = _make_event(entities_mentioned=["NA"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "supplier:NA"),
        }

    def test_priority_order_region_beats_product(self) -> None:
        # Edge case: a product id that happens to equal a Region value.
        # Rule 2 (region) wins over rule 3 (product).
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_order(product_id="EMEA")))
        event = _make_event(entities_mentioned=["EMEA"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "region:EMEA"),
        }

    def test_unresolved_mention_increments_counter_and_emits_no_edge(self) -> None:
        adapter = SupplyChainKGAdapter()
        event = _make_event(entities_mentioned=["GHOST-X", "SUP-Z"])

        edges = list(adapter.to_edges(event))

        assert edges == []
        assert dict(adapter.counters()) == {"unresolved_mentions": 2}

    def test_mixed_resolved_and_unresolved_only_emits_resolved(self) -> None:
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_supplier("SUP-A")))
        event = _make_event(entities_mentioned=["SUP-A", "GHOST-X", "EMEA"])

        edges = list(adapter.to_edges(event))

        assert _edge_keys(edges) == {
            ("event_signal:E1", "MENTIONS", "supplier:SUP-A"),
            ("event_signal:E1", "MENTIONS", "region:EMEA"),
        }
        assert dict(adapter.counters()) == {"unresolved_mentions": 1}


# ---------------------------------------------------------------------------
# Ordering contract
# ---------------------------------------------------------------------------


class TestOrderingContract:
    def test_event_before_supplier_yields_unresolved(self) -> None:
        # Documents the consequence of violating the caller-side ordering:
        # if an EventSignal mentions a Supplier that has not yet been
        # passed through to_nodes, the mention is silently unresolved.
        adapter = SupplyChainKGAdapter()
        event = _make_event(entities_mentioned=["SUP-A"])

        edges_before = list(adapter.to_edges(event))
        # Now feed the supplier — too late for this event.
        list(adapter.to_nodes(_make_supplier("SUP-A")))

        # A second pass over the SAME event would resolve, because the
        # supplier is now in the seen set. The user's responsibility.
        edges_after = list(adapter.to_edges(event))

        assert edges_before == []
        assert _edge_keys(edges_after) == {
            ("event_signal:E1", "MENTIONS", "supplier:SUP-A"),
        }
        assert dict(adapter.counters()) == {"unresolved_mentions": 1}


# ---------------------------------------------------------------------------
# Determinism / idempotency
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_to_nodes_is_deterministic_across_calls(self) -> None:
        adapter = SupplyChainKGAdapter()
        order = _make_order()

        first = list(adapter.to_nodes(order))
        second = list(adapter.to_nodes(order))

        assert first == second

    def test_to_edges_is_deterministic_across_calls(self) -> None:
        adapter = SupplyChainKGAdapter()
        list(adapter.to_nodes(_make_supplier("SUP-A")))
        event = _make_event(entities_mentioned=["SUP-A", "EMEA"])

        first = list(adapter.to_edges(event))
        second = list(adapter.to_edges(event))

        assert first == second


# ---------------------------------------------------------------------------
# Type guard
# ---------------------------------------------------------------------------


class TestTypeGuard:
    def test_to_nodes_rejects_foreign_entity(self) -> None:
        adapter = SupplyChainKGAdapter()
        with pytest.raises(TypeError, match="cannot project"):
            list(adapter.to_nodes("not an entity"))  # type: ignore[arg-type]

    def test_to_edges_rejects_foreign_entity(self) -> None:
        adapter = SupplyChainKGAdapter()
        with pytest.raises(TypeError, match="cannot project"):
            list(adapter.to_edges(42))  # type: ignore[arg-type]
