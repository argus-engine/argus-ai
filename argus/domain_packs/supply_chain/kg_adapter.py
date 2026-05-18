# SPDX-License-Identifier: Apache-2.0
"""Supply-chain :class:`KGAdapter`: project four entities into typed graph elements.

Maps each :class:`Supplier`, :class:`Order`, :class:`Shipment`, and
:class:`EventSignal` to the :class:`KGNode` and :class:`KGEdge` instances
the platform-core builder forwards to whichever backend is configured.
The mapping follows the layering in
:mod:`argus.platform_core.kg.schema`: foreign-key fields become typed
edges, scalar fields stay as node properties.

Field-to-graph mapping
----------------------

+------------------------------------+----------------------------------+
| Source field                       | Graph element                    |
+====================================+==================================+
| ``Supplier.supplier_id``           | :class:`SUPPLIER` node           |
+------------------------------------+----------------------------------+
| ``Supplier.region``                | ``LOCATED_IN`` → REGION          |
+------------------------------------+----------------------------------+
| ``Order.order_id``                 | :class:`ORDER` node              |
+------------------------------------+----------------------------------+
| ``Order.supplier_id``              | ``HAS_SUPPLIER`` → SUPPLIER      |
+------------------------------------+----------------------------------+
| ``Order.product_id``               | ``OF_PRODUCT`` → PRODUCT         |
+------------------------------------+----------------------------------+
| ``Order.customer_id``              | ``PLACED_BY`` → CUSTOMER         |
+------------------------------------+----------------------------------+
| ``Order.destination_region``       | ``SHIPS_TO`` → REGION            |
+------------------------------------+----------------------------------+
| ``Shipment.shipment_id``           | :class:`SHIPMENT` node           |
+------------------------------------+----------------------------------+
| ``Shipment.order_id``              | ``FULFILS_ORDER`` → ORDER        |
+------------------------------------+----------------------------------+
| ``Shipment.supplier_id``           | ``SUPPLIED_BY`` → SUPPLIER       |
+------------------------------------+----------------------------------+
| ``EventSignal.event_id``           | :class:`EVENT_SIGNAL` node       |
+------------------------------------+----------------------------------+
| ``EventSignal.entities_mentioned`` | ``MENTIONS`` → resolved node     |
+------------------------------------+----------------------------------+

Notes:

- :class:`Shipment` does **not** emit a ``SHIPS_TO`` edge: its
  ``destination_location`` is a free-form UN/LOCODE or city string, not
  a :class:`Region` enum value. The order's destination region is
  reachable transitively through ``FULFILS_ORDER → Order → SHIPS_TO``.
- :class:`Order.supplier_id` is optional; when ``None`` the
  ``HAS_SUPPLIER`` edge is skipped. The KG tolerates dangling FKs (real
  data streams arrive out of order); a resolved supplier may appear
  later through a sibling source.
- :class:`Decimal` properties (``Order.unit_price``) are stored as
  ``str`` to preserve precision across the Neo4j driver, which rejects
  Decimal. Reconstruct with ``Decimal(s)`` on read.
- Enum properties (``OrderStatus``, ``ShippingMode``, ``ShipmentStatus``,
  ``EventCategory``, ``EventSeverity``) are stored as their string
  ``.value`` so JSON / Cypher serialisation is identical on both
  backends.

Entity resolution for ``EventSignal.entities_mentioned``
--------------------------------------------------------

For each opaque string in :attr:`EventSignal.entities_mentioned`, the
adapter tries four matchers in order, first match wins:

1. Exact match against a Supplier ID seen so far in this build
2. Exact match against a :class:`Region` enum value
3. Exact match against a Product ID seen so far in this build
4. Exact match against a Customer ID seen so far in this build

A match emits a ``MENTIONS`` edge from the event to the resolved node.
A miss increments ``unresolved_mentions`` on the adapter (surfaced via
:meth:`counters`) and is logged at WARNING level. The graph is not
polluted with placeholder nodes.

Caller-side ordering contract
-----------------------------

Because resolution scans only entities **seen so far in this build**,
the caller MUST feed entities in the order::

    Suppliers → Orders → Shipments → EventSignals

If an EventSignal arrives before the entity it mentions, the mention is
treated as unresolved (counter increments, no edge). The end-to-end
ingestion test enforces this order; the canonical fixture set wires up
that order via :func:`build_supply_chain_kg`.

Construct one :class:`SupplyChainKGAdapter` per build. Reusing an
adapter instance across separate builds leaks state across builds and
is a bug.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

from argus.domain_packs.supply_chain.data.schemas import (
    EventSignal,
    Order,
    Region,
    Shipment,
    Supplier,
)
from argus.platform_core.kg.schema import (
    EdgeType,
    KGEdge,
    KGNode,
    NodeType,
    make_edge_id,
    make_node_id,
)

SupplyChainEntity = Supplier | Order | Shipment | EventSignal
"""Union of the four entity types this adapter handles."""

_REGION_VALUES: frozenset[str] = frozenset(r.value for r in Region)
"""Set of all :class:`Region` enum values, used for fast mention resolution."""

logger = logging.getLogger(__name__)


class SupplyChainKGAdapter:
    """Project supply-chain Pydantic entities into typed KG nodes and edges.

    Stateful: as the builder feeds entities through :meth:`to_nodes` /
    :meth:`to_edges`, the adapter records the IDs of supplier, product,
    and customer nodes it has projected. Subsequent :class:`EventSignal`
    entities resolve :attr:`EventSignal.entities_mentioned` strings
    against those accumulated sets.

    See the module docstring for the full field-to-graph mapping table
    and the caller-side ordering contract that resolution relies on.
    """

    __slots__ = (
        "_seen_customers",
        "_seen_products",
        "_seen_suppliers",
        "_unresolved_mentions",
    )

    def __init__(self) -> None:
        self._seen_suppliers: set[str] = set()
        self._seen_products: set[str] = set()
        self._seen_customers: set[str] = set()
        self._unresolved_mentions: int = 0

    # ------------------------------------------------------------------
    # KGAdapter Protocol surface
    # ------------------------------------------------------------------

    def to_nodes(self, entity: SupplyChainEntity) -> Iterable[KGNode]:
        """Project ``entity`` into the nodes it implies."""
        if isinstance(entity, Supplier):
            yield from self._supplier_nodes(entity)
        elif isinstance(entity, Order):
            yield from self._order_nodes(entity)
        elif isinstance(entity, Shipment):
            yield from self._shipment_nodes(entity)
        elif isinstance(entity, EventSignal):
            yield from self._event_signal_nodes(entity)
        else:
            raise TypeError(
                f"SupplyChainKGAdapter cannot project {type(entity).__name__!r}; "
                f"expected Supplier, Order, Shipment, or EventSignal."
            )

    def to_edges(self, entity: SupplyChainEntity) -> Iterable[KGEdge]:
        """Project ``entity`` into the edges it implies."""
        if isinstance(entity, Supplier):
            yield from self._supplier_edges(entity)
        elif isinstance(entity, Order):
            yield from self._order_edges(entity)
        elif isinstance(entity, Shipment):
            yield from self._shipment_edges(entity)
        elif isinstance(entity, EventSignal):
            yield from self._event_signal_edges(entity)
        else:
            raise TypeError(
                f"SupplyChainKGAdapter cannot project {type(entity).__name__!r}; "
                f"expected Supplier, Order, Shipment, or EventSignal."
            )

    def counters(self) -> Mapping[str, int]:
        """Return ``{"unresolved_mentions": N}`` for this build."""
        return {"unresolved_mentions": self._unresolved_mentions}

    # ------------------------------------------------------------------
    # Supplier
    # ------------------------------------------------------------------

    def _supplier_nodes(self, supplier: Supplier) -> Iterable[KGNode]:
        self._seen_suppliers.add(supplier.supplier_id)
        properties: dict[str, object] = {
            "name": supplier.name,
            "country": supplier.country,
            "tier": supplier.tier,
        }
        if supplier.industry_sic is not None:
            properties["industry_sic"] = supplier.industry_sic
        if supplier.ticker is not None:
            properties["ticker"] = supplier.ticker
        if supplier.cik is not None:
            properties["cik"] = supplier.cik
        yield KGNode(
            id=make_node_id(NodeType.SUPPLIER, supplier.supplier_id),
            type=NodeType.SUPPLIER,
            properties=properties,
        )
        yield _region_node(supplier.region)

    def _supplier_edges(self, supplier: Supplier) -> Iterable[KGEdge]:
        supplier_id = make_node_id(NodeType.SUPPLIER, supplier.supplier_id)
        region_id = make_node_id(NodeType.REGION, supplier.region.value)
        yield KGEdge(
            id=make_edge_id(supplier_id, EdgeType.LOCATED_IN, region_id),
            source_id=supplier_id,
            target_id=region_id,
            type=EdgeType.LOCATED_IN,
        )

    # ------------------------------------------------------------------
    # Order
    # ------------------------------------------------------------------

    def _order_nodes(self, order: Order) -> Iterable[KGNode]:
        self._seen_products.add(order.product_id)
        self._seen_customers.add(order.customer_id)
        properties: dict[str, object] = {
            "quantity": order.quantity,
            "unit_price": str(order.unit_price),
            "currency": order.currency,
            "placed_at": order.placed_at,
            "status": order.status.value,
        }
        yield KGNode(
            id=make_node_id(NodeType.ORDER, order.order_id),
            type=NodeType.ORDER,
            properties=properties,
        )
        yield KGNode(
            id=make_node_id(NodeType.PRODUCT, order.product_id),
            type=NodeType.PRODUCT,
        )
        yield KGNode(
            id=make_node_id(NodeType.CUSTOMER, order.customer_id),
            type=NodeType.CUSTOMER,
        )
        yield _region_node(order.destination_region)

    def _order_edges(self, order: Order) -> Iterable[KGEdge]:
        order_id = make_node_id(NodeType.ORDER, order.order_id)
        product_id = make_node_id(NodeType.PRODUCT, order.product_id)
        customer_id = make_node_id(NodeType.CUSTOMER, order.customer_id)
        region_id = make_node_id(NodeType.REGION, order.destination_region.value)

        yield KGEdge(
            id=make_edge_id(order_id, EdgeType.OF_PRODUCT, product_id),
            source_id=order_id,
            target_id=product_id,
            type=EdgeType.OF_PRODUCT,
        )
        yield KGEdge(
            id=make_edge_id(order_id, EdgeType.PLACED_BY, customer_id),
            source_id=order_id,
            target_id=customer_id,
            type=EdgeType.PLACED_BY,
        )
        yield KGEdge(
            id=make_edge_id(order_id, EdgeType.SHIPS_TO, region_id),
            source_id=order_id,
            target_id=region_id,
            type=EdgeType.SHIPS_TO,
        )
        if order.supplier_id is not None:
            supplier_id = make_node_id(NodeType.SUPPLIER, order.supplier_id)
            yield KGEdge(
                id=make_edge_id(order_id, EdgeType.HAS_SUPPLIER, supplier_id),
                source_id=order_id,
                target_id=supplier_id,
                type=EdgeType.HAS_SUPPLIER,
            )

    # ------------------------------------------------------------------
    # Shipment
    # ------------------------------------------------------------------

    def _shipment_nodes(self, shipment: Shipment) -> Iterable[KGNode]:
        properties: dict[str, object] = {
            "origin_location": shipment.origin_location,
            "destination_location": shipment.destination_location,
            "shipping_mode": shipment.shipping_mode.value,
            "scheduled_departure": shipment.scheduled_departure,
            "scheduled_arrival": shipment.scheduled_arrival,
            "status": shipment.status.value,
            "units": shipment.units,
        }
        if shipment.actual_departure is not None:
            properties["actual_departure"] = shipment.actual_departure
        if shipment.actual_arrival is not None:
            properties["actual_arrival"] = shipment.actual_arrival
        yield KGNode(
            id=make_node_id(NodeType.SHIPMENT, shipment.shipment_id),
            type=NodeType.SHIPMENT,
            properties=properties,
        )

    def _shipment_edges(self, shipment: Shipment) -> Iterable[KGEdge]:
        shipment_id = make_node_id(NodeType.SHIPMENT, shipment.shipment_id)
        order_id = make_node_id(NodeType.ORDER, shipment.order_id)
        supplier_id = make_node_id(NodeType.SUPPLIER, shipment.supplier_id)

        yield KGEdge(
            id=make_edge_id(shipment_id, EdgeType.FULFILS_ORDER, order_id),
            source_id=shipment_id,
            target_id=order_id,
            type=EdgeType.FULFILS_ORDER,
        )
        yield KGEdge(
            id=make_edge_id(shipment_id, EdgeType.SUPPLIED_BY, supplier_id),
            source_id=shipment_id,
            target_id=supplier_id,
            type=EdgeType.SUPPLIED_BY,
        )

    # ------------------------------------------------------------------
    # EventSignal
    # ------------------------------------------------------------------

    def _event_signal_nodes(self, event: EventSignal) -> Iterable[KGNode]:
        properties: dict[str, object] = {
            "title": event.title,
            "summary": event.summary,
            "category": event.category.value,
            "severity": event.severity.value,
            "source_name": event.source_name,
            "occurred_at": event.occurred_at,
        }
        if event.source_url is not None:
            properties["source_url"] = event.source_url
        yield KGNode(
            id=make_node_id(NodeType.EVENT_SIGNAL, event.event_id),
            type=NodeType.EVENT_SIGNAL,
            properties=properties,
        )

    def _event_signal_edges(self, event: EventSignal) -> Iterable[KGEdge]:
        event_id = make_node_id(NodeType.EVENT_SIGNAL, event.event_id)
        for mention in event.entities_mentioned:
            resolved = self._resolve_mention(mention)
            if resolved is None:
                self._unresolved_mentions += 1
                logger.warning(
                    "unresolved EventSignal mention: event_id=%s mention=%r",
                    event.event_id,
                    mention,
                )
                continue
            node_type, key = resolved
            target_id = make_node_id(node_type, key)
            yield KGEdge(
                id=make_edge_id(event_id, EdgeType.MENTIONS, target_id),
                source_id=event_id,
                target_id=target_id,
                type=EdgeType.MENTIONS,
            )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _resolve_mention(self, key: str) -> tuple[NodeType, str] | None:
        """Resolve an :attr:`EventSignal.entities_mentioned` string to a node.

        Tries the four matchers in priority order; returns the
        ``(NodeType, source_key)`` of the first match or ``None`` if no
        rule matched. The ``source_key`` is the input string unchanged —
        the caller composes it into a full node id via
        :func:`make_node_id`.
        """
        if key in self._seen_suppliers:
            return (NodeType.SUPPLIER, key)
        if key in _REGION_VALUES:
            return (NodeType.REGION, key)
        if key in self._seen_products:
            return (NodeType.PRODUCT, key)
        if key in self._seen_customers:
            return (NodeType.CUSTOMER, key)
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _region_node(region: Region) -> KGNode:
    """Return the :class:`REGION` node corresponding to ``region``.

    The same Region appears across many entities (suppliers and orders
    in different parts of the build), so projection is centralised here
    to keep the node payload identical regardless of which entity
    synthesised it. The backend's upsert merge then deduplicates by ID.
    """
    return KGNode(
        id=make_node_id(NodeType.REGION, region.value),
        type=NodeType.REGION,
    )


__all__ = [
    "SupplyChainEntity",
    "SupplyChainKGAdapter",
]
