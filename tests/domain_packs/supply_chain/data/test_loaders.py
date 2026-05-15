# SPDX-License-Identifier: Apache-2.0
"""Tests for the supply-chain loaders.

Round-trip fixture CSVs through each loader and assert the typed
entities come out the other side correctly normalized.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from argus.domain_packs.supply_chain.data import (
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
    load_events,
    load_orders,
    load_shipments,
    load_suppliers,
)


@pytest.fixture()
def supply_chain_fixtures(fixtures_dir: Path) -> Path:
    return fixtures_dir / "supply_chain"


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class TestLoadOrders:
    def test_loads_all_rows(self, supply_chain_fixtures: Path) -> None:
        orders = list(load_orders(supply_chain_fixtures / "orders.csv"))
        assert len(orders) == 4
        assert all(isinstance(o, Order) for o in orders)

    def test_first_row_round_trip(self, supply_chain_fixtures: Path) -> None:
        first = next(iter(load_orders(supply_chain_fixtures / "orders.csv")))
        assert first.order_id == "ORD-1001"
        assert first.customer_id == "C001"
        assert first.quantity == 2
        assert first.unit_price == Decimal("24.99")
        assert first.currency == "USD"
        assert first.placed_at == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert first.status is OrderStatus.CONFIRMED
        assert first.destination_region is Region.EMEA
        assert first.supplier_id == "SUP001"

    def test_empty_supplier_id_becomes_none(self, supply_chain_fixtures: Path) -> None:
        orders = list(load_orders(supply_chain_fixtures / "orders.csv"))
        cancelled = next(o for o in orders if o.status is OrderStatus.CANCELLED)
        assert cancelled.supplier_id is None

    def test_line_total_correct(self, supply_chain_fixtures: Path) -> None:
        orders = list(load_orders(supply_chain_fixtures / "orders.csv"))
        first = orders[0]
        assert first.line_total == Decimal("49.98")  # 2 * 24.99

    def test_raw_field_captures_source_row(self, supply_chain_fixtures: Path) -> None:
        first = next(iter(load_orders(supply_chain_fixtures / "orders.csv")))
        assert first.raw["order_id"] == "ORD-1001"
        assert first.raw["unit_price"] == "24.99"  # raw stays as string


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


class TestLoadSuppliers:
    def test_loads_all_rows(self, supply_chain_fixtures: Path) -> None:
        suppliers = list(load_suppliers(supply_chain_fixtures / "suppliers.csv"))
        assert len(suppliers) == 3
        assert all(isinstance(s, Supplier) for s in suppliers)

    def test_public_supplier_has_ticker_and_cik(
        self, supply_chain_fixtures: Path
    ) -> None:
        suppliers = list(load_suppliers(supply_chain_fixtures / "suppliers.csv"))
        bayside = next(s for s in suppliers if s.supplier_id == "SUP002")
        assert bayside.ticker == "BSM"
        assert bayside.cik == "0000123456"
        assert bayside.region is Region.NA

    def test_private_supplier_has_no_ticker(
        self, supply_chain_fixtures: Path
    ) -> None:
        suppliers = list(load_suppliers(supply_chain_fixtures / "suppliers.csv"))
        acme = next(s for s in suppliers if s.supplier_id == "SUP001")
        assert acme.ticker is None
        assert acme.cik is None

    def test_tier_parsed_as_int(self, supply_chain_fixtures: Path) -> None:
        suppliers = list(load_suppliers(supply_chain_fixtures / "suppliers.csv"))
        penang = next(s for s in suppliers if s.supplier_id == "SUP003")
        assert penang.tier == 2


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------


class TestLoadShipments:
    def test_loads_all_rows(self, supply_chain_fixtures: Path) -> None:
        shipments = list(load_shipments(supply_chain_fixtures / "shipments.csv"))
        assert len(shipments) == 3
        assert all(isinstance(s, Shipment) for s in shipments)

    def test_late_delivery_is_delayed(self, supply_chain_fixtures: Path) -> None:
        shipments = list(load_shipments(supply_chain_fixtures / "shipments.csv"))
        late = next(s for s in shipments if s.shipment_id == "SHIP-001")
        # actual_arrival 2024-01-23T04:15 > scheduled 2024-01-22T00:00
        assert late.is_delayed is True
        assert late.arrival_delay_minutes == 28 * 60 + 15  # 28h15m late

    def test_early_delivery_not_delayed(self, supply_chain_fixtures: Path) -> None:
        shipments = list(load_shipments(supply_chain_fixtures / "shipments.csv"))
        early = next(s for s in shipments if s.shipment_id == "SHIP-002")
        assert early.is_delayed is False
        assert early.arrival_delay_minutes == -15

    def test_in_transit_has_no_actual_times(
        self, supply_chain_fixtures: Path
    ) -> None:
        shipments = list(load_shipments(supply_chain_fixtures / "shipments.csv"))
        in_transit = next(s for s in shipments if s.shipment_id == "SHIP-003")
        assert in_transit.actual_departure is None
        assert in_transit.actual_arrival is None
        assert in_transit.is_delayed is False
        assert in_transit.arrival_delay_minutes is None

    def test_shipping_mode_round_trip(self, supply_chain_fixtures: Path) -> None:
        shipments = list(load_shipments(supply_chain_fixtures / "shipments.csv"))
        modes = {s.shipping_mode for s in shipments}
        assert modes == {ShippingMode.SEA, ShippingMode.ROAD}

    def test_status_round_trip(self, supply_chain_fixtures: Path) -> None:
        shipments = list(load_shipments(supply_chain_fixtures / "shipments.csv"))
        statuses = {s.status for s in shipments}
        assert statuses == {ShipmentStatus.DELIVERED, ShipmentStatus.IN_TRANSIT}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class TestLoadEvents:
    def test_loads_all_rows(self, supply_chain_fixtures: Path) -> None:
        events = list(load_events(supply_chain_fixtures / "events.csv"))
        assert len(events) == 4
        assert all(isinstance(e, EventSignal) for e in events)

    def test_first_event_round_trip(self, supply_chain_fixtures: Path) -> None:
        first = next(iter(load_events(supply_chain_fixtures / "events.csv")))
        assert first.event_id == "EVT-001"
        assert first.occurred_at == datetime(2024, 1, 14, 8, 30, tzinfo=timezone.utc)
        assert first.category is EventCategory.DISRUPTION
        assert first.severity is EventSeverity.HIGH
        assert first.source_name == "GDELT"
        assert first.source_url == "https://example.com/gdelt/1"
        assert first.entities_mentioned == ["USLAX", "SUP002"]

    def test_empty_source_url_becomes_none(self, supply_chain_fixtures: Path) -> None:
        events = list(load_events(supply_chain_fixtures / "events.csv"))
        weather = next(e for e in events if e.event_id == "EVT-003")
        assert weather.source_url is None
        assert weather.entities_mentioned == ["MY", "SUP003"]

    def test_empty_entities_mentioned_becomes_empty_list(
        self, supply_chain_fixtures: Path
    ) -> None:
        events = list(load_events(supply_chain_fixtures / "events.csv"))
        no_entities = next(e for e in events if e.event_id == "EVT-004")
        assert no_entities.entities_mentioned == []

    def test_severity_distribution(self, supply_chain_fixtures: Path) -> None:
        events = list(load_events(supply_chain_fixtures / "events.csv"))
        severities = [e.severity for e in events]
        assert severities == [
            EventSeverity.HIGH,
            EventSeverity.MEDIUM,
            EventSeverity.LOW,
            EventSeverity.INFO,
        ]
