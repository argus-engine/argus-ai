# SPDX-License-Identifier: Apache-2.0
"""Normalized Pydantic schemas for the supply-chain domain pack.

These four models — :class:`Order`, :class:`Supplier`, :class:`Shipment`,
:class:`EventSignal` — are the contract between raw upstream sources
(DataCo, GDELT, SEC EDGAR) and everything downstream (KG construction,
feature engineering, predictive heads, RAG evidence retrieval). Once a
record is normalized into one of these shapes it should round-trip
through the rest of the platform without further modality-specific
knowledge.

Design rules:

- All datetimes are timezone-aware. Naive timestamps are rejected.
- Money fields use :class:`decimal.Decimal` — float drift is unacceptable
  for an audit-traceable platform.
- Each schema carries a ``raw`` field with the source row for audit. This
  is redundant by design: it lets a reviewer reconstruct exactly what
  the connector saw, including columns we did not normalize.
- Cross-entity references (``Order.supplier_id``, ``Shipment.order_id``,
  etc.) are plain string IDs — referential integrity is enforced by the
  KG layer, not at the Pydantic boundary, because data often arrives
  out of order.
- Enums use :class:`str` so they serialize cleanly to JSON without
  custom encoders.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid")


def _require_tz_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("datetime fields must be timezone-aware")
    return value


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Region(str, Enum):
    """Macro region used for grouping orders, suppliers, and shipments."""

    EMEA = "EMEA"
    APAC = "APAC"
    NA = "NA"
    LATAM = "LATAM"
    AFRICA = "AFRICA"
    OTHER = "OTHER"


class OrderStatus(str, Enum):
    """Lifecycle state of an :class:`Order` line."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class ShippingMode(str, Enum):
    """Transport modality for a :class:`Shipment`."""

    AIR = "air"
    SEA = "sea"
    RAIL = "rail"
    ROAD = "road"


class ShipmentStatus(str, Enum):
    """Lifecycle state of a :class:`Shipment`."""

    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class EventSeverity(str, Enum):
    """Severity tier for an :class:`EventSignal`."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventCategory(str, Enum):
    """Top-level event taxonomy for the :class:`EventSignal` stream."""

    DISRUPTION = "disruption"       # port closures, strikes, plant incidents
    FILING = "filing"               # SEC 10-K, 8-K, material event disclosures
    NEWS = "news"                   # general media coverage
    WEATHER = "weather"             # severe weather events
    GEOPOLITICAL = "geopolitical"   # sanctions, tariffs, conflicts
    FINANCIAL = "financial"         # credit events, defaults


# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------


class Supplier(BaseModel):
    """A normalized supplier entity.

    Suppliers are the spine of the supply-chain knowledge graph: orders
    flow toward them, shipments originate from them, and event signals
    are joined to them via :attr:`EventSignal.entities_mentioned`.
    """

    model_config = _FROZEN

    supplier_id: str = Field(..., min_length=1, description="Stable identifier across sources.")
    name: str = Field(..., min_length=1)
    country: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code.",
    )
    region: Region
    tier: int = Field(default=1, ge=1, description="1 = direct supplier, 2 = sub-supplier, ...")
    industry_sic: str | None = Field(default=None, description="SIC code (when matched to EDGAR).")
    ticker: str | None = Field(default=None, description="Stock ticker if publicly traded.")
    cik: str | None = Field(default=None, description="SEC Central Index Key.")
    raw: dict[str, Any] = Field(default_factory=dict, description="Source row for audit.")


class Order(BaseModel):
    """A normalized customer order line.

    DataCo's source rows are item-level (one row per ordered SKU), so
    an ``Order`` instance represents a single product line within a
    customer's transaction. The customer-level grouping is recoverable
    via ``customer_id`` + ``placed_at``, but is not materialized here —
    matching the source grain keeps the platform honest about what it
    has actually observed.
    """

    model_config = _FROZEN

    order_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)
    unit_price: Decimal = Field(..., ge=0, description="Price per unit in ``currency``.")
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code.",
    )
    placed_at: datetime = Field(..., description="When the order was placed (tz-aware).")
    status: OrderStatus
    destination_region: Region
    supplier_id: str | None = Field(
        default=None,
        description="Resolved supplier when the source provides it; the KG fills the gap otherwise.",
    )
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("placed_at")
    @classmethod
    def _placed_at_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("placed_at must be timezone-aware")
        return value

    @property
    def line_total(self) -> Decimal:
        """Total value of this order line (``quantity * unit_price``)."""
        return Decimal(self.quantity) * self.unit_price


class Shipment(BaseModel):
    """A normalized shipment record linking an order to its physical movement.

    Both ``order_id`` and ``supplier_id`` are plain string FKs. Integrity
    is enforced by the KG layer at construction time, not at this Pydantic
    boundary, because shipments and orders frequently arrive in different
    streams and out of order.
    """

    model_config = _FROZEN

    shipment_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1, description="FK to Order; KG enforces.")
    supplier_id: str = Field(..., min_length=1, description="FK to Supplier; KG enforces.")
    origin_location: str = Field(..., min_length=1, description="UN/LOCODE or free-form origin.")
    destination_location: str = Field(..., min_length=1)
    shipping_mode: ShippingMode
    scheduled_departure: datetime
    actual_departure: datetime | None = None
    scheduled_arrival: datetime
    actual_arrival: datetime | None = None
    status: ShipmentStatus
    units: int = Field(..., ge=1)
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "scheduled_departure",
        "actual_departure",
        "scheduled_arrival",
        "actual_arrival",
    )
    @classmethod
    def _tz_aware(cls, value: datetime | None) -> datetime | None:
        return _require_tz_aware(value)

    @property
    def is_delayed(self) -> bool:
        """Whether the shipment is materially behind schedule.

        True if either the explicit status flag is ``DELAYED`` *or*
        ``actual_arrival`` has already exceeded ``scheduled_arrival``.
        Both are checked because the source data sometimes carries one
        signal but not the other.
        """
        if self.status is ShipmentStatus.DELAYED:
            return True
        if self.actual_arrival is None:
            return False
        return self.actual_arrival > self.scheduled_arrival

    @property
    def arrival_delay_minutes(self) -> int | None:
        """Minutes by which actual arrival missed the scheduled arrival.

        Returns ``None`` when ``actual_arrival`` has not been recorded.
        Negative values indicate early arrival.
        """
        if self.actual_arrival is None:
            return None
        delta = self.actual_arrival - self.scheduled_arrival
        return int(delta.total_seconds() // 60)


class EventSignal(BaseModel):
    """A normalized event signal indicating supply-chain-relevant disruption.

    Sourced from GDELT (geopolitical, disasters, strikes), SEC EDGAR
    (8-K disclosures, material event filings), and curated news feeds.
    The ``entities_mentioned`` field carries opaque string identifiers
    (ticker, supplier_id, country code, port code) that the KG layer
    resolves to typed nodes — keeping the schema layer-agnostic.
    """

    model_config = _FROZEN

    event_id: str = Field(..., min_length=1)
    occurred_at: datetime = Field(..., description="When the event occurred (tz-aware).")
    category: EventCategory
    severity: EventSeverity = Field(default=EventSeverity.INFO)
    source_name: str = Field(
        ...,
        min_length=1,
        description='Origin system: e.g. "GDELT", "EDGAR", "Reuters".',
    )
    source_url: str | None = Field(default=None, description="Canonical URL when one exists.")
    title: str = Field(..., min_length=1, max_length=512)
    summary: str = Field(default="", description="Short human-readable description.")
    entities_mentioned: list[str] = Field(
        default_factory=list,
        description="Opaque identifiers — KG resolves them to typed nodes.",
    )
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


__all__ = [
    "EventCategory",
    "EventSeverity",
    "EventSignal",
    "Order",
    "OrderStatus",
    "Region",
    "Shipment",
    "ShipmentStatus",
    "ShippingMode",
    "Supplier",
]
