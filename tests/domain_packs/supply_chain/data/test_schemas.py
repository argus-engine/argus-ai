# SPDX-License-Identifier: Apache-2.0
"""Tests for the supply-chain Pydantic schemas.

Schema-level behavior — validators, derived properties, immutability —
is exercised here. Loader round-trips live in ``test_loaders.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_T0 = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def _supplier(**overrides: object) -> Supplier:
    defaults: dict[str, object] = {
        "supplier_id": "SUP001",
        "name": "Acme",
        "country": "DE",
        "region": Region.EMEA,
    }
    defaults.update(overrides)
    return Supplier(**defaults)  # type: ignore[arg-type]


def _order(**overrides: object) -> Order:
    defaults: dict[str, object] = {
        "order_id": "ORD-1",
        "customer_id": "C001",
        "product_id": "P-1",
        "quantity": 2,
        "unit_price": Decimal("10.00"),
        "placed_at": _T0,
        "status": OrderStatus.CONFIRMED,
        "destination_region": Region.EMEA,
    }
    defaults.update(overrides)
    return Order(**defaults)  # type: ignore[arg-type]


def _shipment(**overrides: object) -> Shipment:
    defaults: dict[str, object] = {
        "shipment_id": "SHIP-1",
        "order_id": "ORD-1",
        "supplier_id": "SUP001",
        "origin_location": "DEHAM",
        "destination_location": "GBLON",
        "shipping_mode": ShippingMode.SEA,
        "scheduled_departure": _T0,
        "scheduled_arrival": _T0 + timedelta(days=6),
        "status": ShipmentStatus.IN_TRANSIT,
        "units": 5,
    }
    defaults.update(overrides)
    return Shipment(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------


class TestSupplier:
    def test_minimal_valid(self) -> None:
        s = _supplier()
        assert s.supplier_id == "SUP001"
        assert s.tier == 1
        assert s.industry_sic is None

    def test_country_must_be_two_chars(self) -> None:
        with pytest.raises(ValidationError):
            _supplier(country="DEU")
        with pytest.raises(ValidationError):
            _supplier(country="D")

    def test_tier_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _supplier(tier=0)

    def test_is_frozen(self) -> None:
        s = _supplier()
        with pytest.raises(ValidationError):
            s.name = "Tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


class TestOrder:
    def test_minimal_valid(self) -> None:
        o = _order()
        assert o.order_id == "ORD-1"
        assert o.currency == "USD"
        assert o.supplier_id is None

    def test_naive_placed_at_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            _order(placed_at=datetime(2024, 1, 15))  # noqa: DTZ001

    def test_quantity_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _order(quantity=0)
        with pytest.raises(ValidationError):
            _order(quantity=-1)

    def test_unit_price_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            _order(unit_price=Decimal("-1"))

    def test_currency_must_be_three_chars(self) -> None:
        with pytest.raises(ValidationError):
            _order(currency="US")
        with pytest.raises(ValidationError):
            _order(currency="USDOL")

    def test_line_total(self) -> None:
        o = _order(quantity=3, unit_price=Decimal("24.99"))
        assert o.line_total == Decimal("74.97")

    def test_line_total_returns_decimal(self) -> None:
        o = _order(quantity=2, unit_price=Decimal("10.00"))
        assert isinstance(o.line_total, Decimal)

    def test_is_frozen(self) -> None:
        o = _order()
        with pytest.raises(ValidationError):
            o.quantity = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Shipment
# ---------------------------------------------------------------------------


class TestShipment:
    def test_naive_timestamps_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            _shipment(scheduled_departure=datetime(2024, 1, 15))  # noqa: DTZ001
        with pytest.raises(ValidationError, match="timezone-aware"):
            _shipment(actual_arrival=datetime(2024, 1, 15))  # noqa: DTZ001

    def test_is_delayed_when_status_flag_set(self) -> None:
        s = _shipment(status=ShipmentStatus.DELAYED)
        assert s.is_delayed is True

    def test_is_delayed_when_actual_after_scheduled(self) -> None:
        s = _shipment(
            scheduled_arrival=_T0 + timedelta(days=6),
            actual_arrival=_T0 + timedelta(days=7),
            status=ShipmentStatus.DELIVERED,
        )
        assert s.is_delayed is True

    def test_not_delayed_when_on_time(self) -> None:
        s = _shipment(
            scheduled_arrival=_T0 + timedelta(days=6),
            actual_arrival=_T0 + timedelta(days=6),
            status=ShipmentStatus.DELIVERED,
        )
        assert s.is_delayed is False

    def test_not_delayed_when_early(self) -> None:
        s = _shipment(
            scheduled_arrival=_T0 + timedelta(days=6),
            actual_arrival=_T0 + timedelta(days=5),
            status=ShipmentStatus.DELIVERED,
        )
        assert s.is_delayed is False

    def test_not_delayed_when_no_actual_arrival_yet(self) -> None:
        s = _shipment(actual_arrival=None, status=ShipmentStatus.IN_TRANSIT)
        assert s.is_delayed is False

    def test_arrival_delay_minutes_when_late(self) -> None:
        s = _shipment(
            scheduled_arrival=_T0,
            actual_arrival=_T0 + timedelta(minutes=90),
            status=ShipmentStatus.DELIVERED,
        )
        assert s.arrival_delay_minutes == 90

    def test_arrival_delay_minutes_when_early(self) -> None:
        s = _shipment(
            scheduled_arrival=_T0,
            actual_arrival=_T0 - timedelta(minutes=30),
            status=ShipmentStatus.DELIVERED,
        )
        assert s.arrival_delay_minutes == -30

    def test_arrival_delay_minutes_is_none_when_no_actual(self) -> None:
        s = _shipment(actual_arrival=None)
        assert s.arrival_delay_minutes is None


# ---------------------------------------------------------------------------
# EventSignal
# ---------------------------------------------------------------------------


class TestEventSignal:
    def _event(self, **overrides: object) -> EventSignal:
        defaults: dict[str, object] = {
            "event_id": "EVT-1",
            "occurred_at": _T0,
            "category": EventCategory.DISRUPTION,
            "source_name": "GDELT",
            "title": "Port closure",
        }
        defaults.update(overrides)
        return EventSignal(**defaults)  # type: ignore[arg-type]

    def test_minimal_valid(self) -> None:
        e = self._event()
        assert e.severity is EventSeverity.INFO
        assert e.entities_mentioned == []
        assert e.summary == ""

    def test_naive_occurred_at_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            self._event(occurred_at=datetime(2024, 1, 15))  # noqa: DTZ001

    def test_title_required(self) -> None:
        with pytest.raises(ValidationError):
            self._event(title="")

    def test_title_max_length(self) -> None:
        with pytest.raises(ValidationError):
            self._event(title="x" * 513)

    def test_severity_enum_round_trip(self) -> None:
        e = self._event(severity=EventSeverity.CRITICAL)
        assert e.severity is EventSeverity.CRITICAL
        assert e.severity.value == "critical"

    def test_is_frozen(self) -> None:
        e = self._event()
        with pytest.raises(ValidationError):
            e.title = "Tampered"  # type: ignore[misc]
