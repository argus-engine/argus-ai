# SPDX-License-Identifier: Apache-2.0
"""Supply-chain data layer: schemas + loaders.

This is the boundary between the raw source data (DataCo CSVs, GDELT events,
SEC EDGAR filings) and everything downstream. Downstream code never touches
the raw shape — it consumes the normalized Pydantic schemas declared here.

**Modules:**

- `schemas.py` — `Order`, `Supplier`, `Shipment`, `EventSignal` and their
  supporting enumerations (`Region`, `OrderStatus`, `ShippingMode`,
  `ShipmentStatus`, `EventSeverity`, `EventCategory`).
- `loaders.py` — functions composing `argus.platform_core.ingestion`
  connectors into normalized entity instances.
"""

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
