# SPDX-License-Identifier: Apache-2.0
"""Loaders that compose ingestion connectors into normalized supply-chain entities.

Each loader is a thin function: configure the right
:class:`StructuredCSVConnector`, iterate its records, and map each payload
into the corresponding Pydantic schema (``Order``, ``Supplier``,
``Shipment``, ``EventSignal``). The mapping is the only place column-name
expectations live — adjust here, not in the platform core, when an upstream
source changes its column labels.

Phase 1 assumes the upstream CSVs already use the canonical column names
shown in :func:`load_orders` and friends. Real DataCo / GDELT / EDGAR
downloads are renamed to that shape by ``scripts/build_fixtures.py``
(Task #9), keeping the loaders source-format-agnostic.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

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
from argus.platform_core.ingestion.base import RawRecord, parse_timestamp
from argus.platform_core.ingestion.structured import (
    StructuredCSVConfig,
    StructuredCSVConnector,
)


def _none_if_empty(value: str | None) -> str | None:
    """Return ``None`` for empty/whitespace-only strings, otherwise the stripped value."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_optional_timestamp(value: str | None) -> object:
    """Parse a tz-aware timestamp, or return ``None`` for empty input."""
    cleaned = _none_if_empty(value)
    if cleaned is None:
        return None
    return parse_timestamp(cleaned)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def load_orders(
    csv_path: Path,
    *,
    source: str = "supply_chain.orders",
) -> Iterator[Order]:
    """Yield :class:`Order` instances from a CSV with the canonical column shape.

    Canonical columns: ``order_id``, ``customer_id``, ``product_id``,
    ``quantity``, ``unit_price``, ``currency``, ``placed_at``, ``status``,
    ``destination_region``, ``supplier_id``.
    """
    connector = StructuredCSVConnector(
        StructuredCSVConfig(
            name="orders",
            source=source,
            csv_path=csv_path,
            id_column="order_id",
            timestamp_column="placed_at",
        )
    )
    for record in connector.pull():
        yield _record_to_order(record)


def _record_to_order(record: RawRecord) -> Order:
    payload = record.payload
    assert record.timestamp is not None  # connector enforces via timestamp_column
    return Order(
        order_id=record.record_id,
        customer_id=str(payload["customer_id"]),
        product_id=str(payload["product_id"]),
        quantity=int(payload["quantity"]),
        unit_price=Decimal(str(payload["unit_price"])),
        currency=str(payload.get("currency") or "USD"),
        placed_at=record.timestamp,
        status=OrderStatus(str(payload["status"])),
        destination_region=Region(str(payload["destination_region"])),
        supplier_id=_none_if_empty(payload.get("supplier_id")),
        raw=dict(payload),
    )


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


def load_suppliers(
    csv_path: Path,
    *,
    source: str = "supply_chain.suppliers",
) -> Iterator[Supplier]:
    """Yield :class:`Supplier` instances from a canonical-shape CSV.

    Canonical columns: ``supplier_id``, ``name``, ``country``, ``region``,
    ``tier``, ``industry_sic``, ``ticker``, ``cik``.
    """
    connector = StructuredCSVConnector(
        StructuredCSVConfig(
            name="suppliers",
            source=source,
            csv_path=csv_path,
            id_column="supplier_id",
        )
    )
    for record in connector.pull():
        yield _record_to_supplier(record)


def _record_to_supplier(record: RawRecord) -> Supplier:
    payload = record.payload
    return Supplier(
        supplier_id=record.record_id,
        name=str(payload["name"]),
        country=str(payload["country"]),
        region=Region(str(payload["region"])),
        tier=int(payload.get("tier") or 1),
        industry_sic=_none_if_empty(payload.get("industry_sic")),
        ticker=_none_if_empty(payload.get("ticker")),
        cik=_none_if_empty(payload.get("cik")),
        raw=dict(payload),
    )


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------


def load_shipments(
    csv_path: Path,
    *,
    source: str = "supply_chain.shipments",
) -> Iterator[Shipment]:
    """Yield :class:`Shipment` instances from a canonical-shape CSV.

    Canonical columns: ``shipment_id``, ``order_id``, ``supplier_id``,
    ``origin_location``, ``destination_location``, ``shipping_mode``,
    ``scheduled_departure``, ``actual_departure``, ``scheduled_arrival``,
    ``actual_arrival``, ``status``, ``units``.
    """
    connector = StructuredCSVConnector(
        StructuredCSVConfig(
            name="shipments",
            source=source,
            csv_path=csv_path,
            id_column="shipment_id",
        )
    )
    for record in connector.pull():
        yield _record_to_shipment(record)


def _record_to_shipment(record: RawRecord) -> Shipment:
    payload = record.payload
    return Shipment(
        shipment_id=record.record_id,
        order_id=str(payload["order_id"]),
        supplier_id=str(payload["supplier_id"]),
        origin_location=str(payload["origin_location"]),
        destination_location=str(payload["destination_location"]),
        shipping_mode=ShippingMode(str(payload["shipping_mode"])),
        scheduled_departure=parse_timestamp(str(payload["scheduled_departure"])),
        actual_departure=_parse_optional_timestamp(payload.get("actual_departure")),
        scheduled_arrival=parse_timestamp(str(payload["scheduled_arrival"])),
        actual_arrival=_parse_optional_timestamp(payload.get("actual_arrival")),
        status=ShipmentStatus(str(payload["status"])),
        units=int(payload["units"]),
        raw=dict(payload),
    )


# ---------------------------------------------------------------------------
# Event signals
# ---------------------------------------------------------------------------


_ENTITY_SEPARATOR = "|"
"""Pipe used as the in-cell separator for entities_mentioned in CSV fixtures.

Comma is reserved for the CSV delimiter; pipe is unlikely to appear in real
supplier / port / ticker identifiers.
"""


def load_events(
    csv_path: Path,
    *,
    source: str = "supply_chain.events",
) -> Iterator[EventSignal]:
    """Yield :class:`EventSignal` instances from a canonical-shape CSV.

    Canonical columns: ``event_id``, ``occurred_at``, ``category``,
    ``severity``, ``source_name``, ``source_url``, ``title``, ``summary``,
    ``entities_mentioned`` (pipe-separated).
    """
    connector = StructuredCSVConnector(
        StructuredCSVConfig(
            name="events",
            source=source,
            csv_path=csv_path,
            id_column="event_id",
            timestamp_column="occurred_at",
        )
    )
    for record in connector.pull():
        yield _record_to_event(record)


def _record_to_event(record: RawRecord) -> EventSignal:
    payload = record.payload
    assert record.timestamp is not None
    raw_entities = str(payload.get("entities_mentioned") or "")
    entities = [e.strip() for e in raw_entities.split(_ENTITY_SEPARATOR) if e.strip()]
    return EventSignal(
        event_id=record.record_id,
        occurred_at=record.timestamp,
        category=EventCategory(str(payload["category"])),
        severity=EventSeverity(str(payload.get("severity") or "info")),
        source_name=str(payload["source_name"]),
        source_url=_none_if_empty(payload.get("source_url")),
        title=str(payload["title"]),
        summary=str(payload.get("summary") or ""),
        entities_mentioned=entities,
        raw=dict(payload),
    )


__all__ = [
    "load_events",
    "load_orders",
    "load_shipments",
    "load_suppliers",
]
