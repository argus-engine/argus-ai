# SPDX-License-Identifier: Apache-2.0
"""Deterministic supply-chain fixture for the flagship cascade + subgraph tests.

This module is *the test contract* for the supply-chain flagship tests.
Its topology was designed by hand to produce specific, hand-traceable
query results — the flagship tests consume the named ``EXPECTED_*``
constants below rather than embedding magic numbers. If you change the
topology, you MUST re-trace by hand and update the constants in lockstep.

Test-design rationale
---------------------

Both ``cascading_risk`` and ``subgraph`` traverse the graph
bidirectionally: KG edges encode foreign-key direction, not
impact-propagation direction, so a disruption at a supplier reaches its
upstream orders by walking incoming ``HAS_SUPPLIER`` edges. A test
that only asserts inclusions ("SUP-A's cascade reaches CUST-1") would
silently pass against a buggy implementation that walks too far. The
topology therefore embeds an **isolated control supplier (SUP-B)**:

- SUP-A and SUP-B share no direct edges.
- The only path between the two halves runs through ``Region:NA`` —
  SH-O4 (a SUP-A shipment) and O4 (a SUP-A order) both reach NA, and
  SH-O5 / O5 (the SUP-B side) also touch NA. NA is therefore reachable
  from SUP-A at hop 2; SUP-B itself is reachable only at hop 3+.
- At ``max_hops=2``, the cascade from SUP-A MUST stop before crossing
  NA into the SUP-B side. The flagship cascade test asserts both
  inclusions and exclusions — the five-node exclusion set
  (SUP-B, O5, P3, SH-O5, E2) is what proves the BFS hop limit is
  enforced, not just that the BFS runs. E2 is in the exclusion set
  because it ``MENTIONS`` SUP-B and P3, which structurally places it
  on the SUP-B side (E2 is reached at hop 4 via SUP-B).

EventSignals further exercise the adapter's unresolved-mention counter:
E1 mentions a known SUP-A and EMEA plus one ghost string; E3 mentions
two ghost strings. Total unresolved across the build: 3.

Topology
--------

::

    Suppliers   ──LOCATED_IN──>  Regions
    SUP-A                        EMEA
    SUP-B                        NA

    Orders   product  customer  supplier  destination
    O1       P1       CUST-1    SUP-A     EMEA
    O2       P1       CUST-2    SUP-A     EMEA
    O3       P2       CUST-1    SUP-A     EMEA
    O4       P2       CUST-3    SUP-A     NA     ← bridges SUP-A to Region:NA
    O5       P3       CUST-2    SUP-B     NA     ← SUP-B side; control

    Shipments       FULFILS  SUPPLIED_BY
    SH-O1           O1       SUP-A
    SH-O2           O2       SUP-A
    SH-O3           O3       SUP-A
    SH-O4           O4       SUP-A           ← bridges SUP-A to NA via O4
    SH-O5           O5       SUP-B           ← SUP-B side; control

    EventSignals    entities_mentioned (resolution → counter)
    E1              ["SUP-A", "EMEA", "GHOST-X"]
                    → resolves SUP-A (rule 1), EMEA (rule 2);
                      GHOST-X unresolved (+1)
    E2              ["SUP-B", "P3"]
                    → resolves SUP-B (rule 1), P3 (rule 3) (+0)
    E3              ["SUP-Z", "CUST-99"]
                    → both unresolved (+2)

Expected: ``cascading_risk(supplier:SUP-A, max_hops=2)``
--------------------------------------------------------

Sorted by ``(hops, target_id)``. **16 RiskPaths total** — the
plan-readback approximated 15; the exact hand-trace is 16, the
discrepancy being ``region:NA`` reached at hop 2 (via the SH-O4 / O4
SHIPS_TO edges). The control set (SUP-B side) is unchanged.

Hop 1 — 10 nodes touched by edges incident on SUP-A::

    event_signal:E1
    order:O1, order:O2, order:O3, order:O4
    region:EMEA
    shipment:SH-O1, shipment:SH-O2, shipment:SH-O3, shipment:SH-O4

Hop 2 — 6 new nodes::

    customer:CUST-1, customer:CUST-2, customer:CUST-3
    product:P1, product:P2
    region:NA

Excluded at ``max_hops=2`` (the five-node SUP-B-side control set;
deepest member at hop 4)::

    supplier:SUP-B   (hop 3, via NA -LOCATED_IN- SUP-B)
    order:O5         (hop 3, via NA <-SHIPS_TO- O5)
    product:P3       (hop 4, via O5 -OF_PRODUCT-> P3)
    shipment:SH-O5   (hop 4, via O5 / SUP-B)
    event_signal:E2  (hop 4, via SUP-B <-MENTIONS- E2)

Expected: ``subgraph([supplier:SUP-A], max_hops=1)``
-----------------------------------------------------

Nodes — 11 (SUP-A + 10 hop-1 neighbours)::

    supplier:SUP-A,
    order:O1, order:O2, order:O3, order:O4,
    shipment:SH-O1, shipment:SH-O2, shipment:SH-O3, shipment:SH-O4,
    event_signal:E1,
    region:EMEA

Induced edges — 18 (every edge between any two of those 11)::

    supplier:SUP-A   -LOCATED_IN->   region:EMEA
    order:O1         -HAS_SUPPLIER-> supplier:SUP-A
    order:O1         -SHIPS_TO->     region:EMEA
    order:O2         -HAS_SUPPLIER-> supplier:SUP-A
    order:O2         -SHIPS_TO->     region:EMEA
    order:O3         -HAS_SUPPLIER-> supplier:SUP-A
    order:O3         -SHIPS_TO->     region:EMEA
    order:O4         -HAS_SUPPLIER-> supplier:SUP-A
    shipment:SH-O1   -FULFILS_ORDER->order:O1
    shipment:SH-O1   -SUPPLIED_BY->  supplier:SUP-A
    shipment:SH-O2   -FULFILS_ORDER->order:O2
    shipment:SH-O2   -SUPPLIED_BY->  supplier:SUP-A
    shipment:SH-O3   -FULFILS_ORDER->order:O3
    shipment:SH-O3   -SUPPLIED_BY->  supplier:SUP-A
    shipment:SH-O4   -FULFILS_ORDER->order:O4
    shipment:SH-O4   -SUPPLIED_BY->  supplier:SUP-A
    event_signal:E1  -MENTIONS->     supplier:SUP-A
    event_signal:E1  -MENTIONS->     region:EMEA

Edges that *leave* the subgraph (e.g. ``order:O1 -OF_PRODUCT-> product:P1``,
``order:O4 -SHIPS_TO-> region:NA``) are excluded — the induced subgraph
retains only edges whose *both* endpoints are in the node set.

Expected: ``IngestionReport.adapter_counters``
-----------------------------------------------

``unresolved_mentions = 3`` (GHOST-X from E1, plus SUP-Z and CUST-99
from E3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
from argus.domain_packs.supply_chain.kg_adapter import SupplyChainEntity

_PLACED = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
_DEP = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
_ARR = datetime(2026, 3, 10, 18, 0, tzinfo=UTC)
_OCCURRED = datetime(2026, 3, 3, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Entity builders
# ---------------------------------------------------------------------------


def build_suppliers() -> list[Supplier]:
    """Two suppliers — SUP-A (EMEA) and SUP-B (NA), no shared edges."""
    return [
        Supplier(
            supplier_id="SUP-A",
            name="Acme Trading",
            country="GB",
            region=Region.EMEA,
            tier=1,
        ),
        Supplier(
            supplier_id="SUP-B",
            name="Beta Logistics",
            country="US",
            region=Region.NA,
            tier=1,
        ),
    ]


def build_orders() -> list[Order]:
    """Five orders — four on SUP-A side (O1..O4), one on SUP-B side (O5)."""

    def _order(
        order_id: str,
        product_id: str,
        customer_id: str,
        supplier_id: str,
        destination_region: Region,
    ) -> Order:
        return Order(
            order_id=order_id,
            customer_id=customer_id,
            product_id=product_id,
            quantity=10,
            unit_price=Decimal("25.00"),
            currency="USD",
            placed_at=_PLACED,
            status=OrderStatus.CONFIRMED,
            destination_region=destination_region,
            supplier_id=supplier_id,
        )

    return [
        _order("O1", "P1", "CUST-1", "SUP-A", Region.EMEA),
        _order("O2", "P1", "CUST-2", "SUP-A", Region.EMEA),
        _order("O3", "P2", "CUST-1", "SUP-A", Region.EMEA),
        _order("O4", "P2", "CUST-3", "SUP-A", Region.NA),
        _order("O5", "P3", "CUST-2", "SUP-B", Region.NA),
    ]


def build_shipments() -> list[Shipment]:
    """Five shipments — one per order."""

    def _shipment(shipment_id: str, order_id: str, supplier_id: str) -> Shipment:
        return Shipment(
            shipment_id=shipment_id,
            order_id=order_id,
            supplier_id=supplier_id,
            origin_location="GBLON",
            destination_location="DEHAM",
            shipping_mode=ShippingMode.SEA,
            scheduled_departure=_DEP,
            scheduled_arrival=_ARR,
            status=ShipmentStatus.IN_TRANSIT,
            units=10,
        )

    return [
        _shipment("SH-O1", "O1", "SUP-A"),
        _shipment("SH-O2", "O2", "SUP-A"),
        _shipment("SH-O3", "O3", "SUP-A"),
        _shipment("SH-O4", "O4", "SUP-A"),
        _shipment("SH-O5", "O5", "SUP-B"),
    ]


def build_event_signals() -> list[EventSignal]:
    """Three event signals exercising the four-rule resolution + unresolved counter."""

    def _event(
        event_id: str, entities_mentioned: list[str], severity: EventSeverity
    ) -> EventSignal:
        return EventSignal(
            event_id=event_id,
            occurred_at=_OCCURRED,
            category=EventCategory.DISRUPTION,
            severity=severity,
            source_name="TestFeed",
            title=f"Test event {event_id}",
            summary="",
            entities_mentioned=entities_mentioned,
        )

    return [
        _event("E1", ["SUP-A", "EMEA", "GHOST-X"], EventSeverity.HIGH),
        _event("E2", ["SUP-B", "P3"], EventSeverity.MEDIUM),
        _event("E3", ["SUP-Z", "CUST-99"], EventSeverity.LOW),
    ]


def build_entity_stream() -> list[SupplyChainEntity]:
    """Return all entities in the canonical ingest order required by the adapter.

    Order: Suppliers → Orders → Shipments → EventSignals. This is the
    caller-side ordering contract that the adapter's mention resolution
    depends on; ingest in any other order and EventSignal mentions
    silently fall into ``unresolved_mentions``.
    """
    return [
        *build_suppliers(),
        *build_orders(),
        *build_shipments(),
        *build_event_signals(),
    ]


# ---------------------------------------------------------------------------
# Expected query results — derived by hand from the topology above
# ---------------------------------------------------------------------------

EXPECTED_CASCADE_FROM_SUP_A_MAX_HOPS_2: tuple[str, ...] = (
    # Hop 1, sorted by target_id
    "event_signal:E1",
    "order:O1",
    "order:O2",
    "order:O3",
    "order:O4",
    "region:EMEA",
    "shipment:SH-O1",
    "shipment:SH-O2",
    "shipment:SH-O3",
    "shipment:SH-O4",
    # Hop 2, sorted by target_id
    "customer:CUST-1",
    "customer:CUST-2",
    "customer:CUST-3",
    "product:P1",
    "product:P2",
    "region:NA",
)
"""Expected target_ids from ``cascading_risk(supplier:SUP-A, max_hops=2)``.

Order is ``(hops, target_id)`` — matches the documented sort order in
:meth:`KGBackend.cascading_risk` (and the explicit sort in both
:class:`NetworkXBackend.cascading_risk` and the Neo4j query).
"""

CASCADE_EXCLUDED_AT_MAX_HOPS_2: frozenset[str] = frozenset(
    {
        "supplier:SUP-B",
        "order:O5",
        "product:P3",
        "shipment:SH-O5",
        "event_signal:E2",
    }
)
"""Nodes that exist in the graph but MUST NOT appear in the SUP-A cascade at hop 2.

Five SUP-B-side nodes. Reaching any of them from SUP-A requires at
least hop 3 (through ``region:NA``); the deepest, ``event_signal:E2``
and ``product:P3`` and ``shipment:SH-O5``, are at hop 4. Asserting
the exclusion is what proves the BFS hop limit is enforced — the
negative-assertion control documented in the module rationale.
"""

EXPECTED_SUBGRAPH_NODE_IDS_FROM_SUP_A_MAX_HOPS_1: frozenset[str] = frozenset(
    {
        "supplier:SUP-A",
        "order:O1",
        "order:O2",
        "order:O3",
        "order:O4",
        "shipment:SH-O1",
        "shipment:SH-O2",
        "shipment:SH-O3",
        "shipment:SH-O4",
        "event_signal:E1",
        "region:EMEA",
    }
)
"""Expected node ids from ``subgraph([supplier:SUP-A], max_hops=1)``."""

EXPECTED_SUBGRAPH_EDGE_KEYS_FROM_SUP_A_MAX_HOPS_1: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("supplier:SUP-A", "LOCATED_IN", "region:EMEA"),
        ("order:O1", "HAS_SUPPLIER", "supplier:SUP-A"),
        ("order:O1", "SHIPS_TO", "region:EMEA"),
        ("order:O2", "HAS_SUPPLIER", "supplier:SUP-A"),
        ("order:O2", "SHIPS_TO", "region:EMEA"),
        ("order:O3", "HAS_SUPPLIER", "supplier:SUP-A"),
        ("order:O3", "SHIPS_TO", "region:EMEA"),
        ("order:O4", "HAS_SUPPLIER", "supplier:SUP-A"),
        ("shipment:SH-O1", "FULFILS_ORDER", "order:O1"),
        ("shipment:SH-O1", "SUPPLIED_BY", "supplier:SUP-A"),
        ("shipment:SH-O2", "FULFILS_ORDER", "order:O2"),
        ("shipment:SH-O2", "SUPPLIED_BY", "supplier:SUP-A"),
        ("shipment:SH-O3", "FULFILS_ORDER", "order:O3"),
        ("shipment:SH-O3", "SUPPLIED_BY", "supplier:SUP-A"),
        ("shipment:SH-O4", "FULFILS_ORDER", "order:O4"),
        ("shipment:SH-O4", "SUPPLIED_BY", "supplier:SUP-A"),
        ("event_signal:E1", "MENTIONS", "supplier:SUP-A"),
        ("event_signal:E1", "MENTIONS", "region:EMEA"),
    }
)
"""Expected induced edges as ``(source_id, edge_type_value, target_id)`` triples.

The induced subgraph contract (documented in :class:`NetworkXBackend.subgraph`
and matched by the Neo4j implementation) retains every edge between any
two collected nodes whose ``type`` passes the optional edge filter —
not only the spanning-tree edges traversed during BFS. So
``order:O1 -SHIPS_TO-> region:EMEA`` is included even though BFS reached
EMEA via ``supplier:SUP-A -LOCATED_IN-> region:EMEA``.
"""

EXPECTED_UNRESOLVED_MENTIONS: int = 3
"""GHOST-X (E1) + SUP-Z (E3) + CUST-99 (E3) — none resolvable."""


__all__ = [
    "CASCADE_EXCLUDED_AT_MAX_HOPS_2",
    "EXPECTED_CASCADE_FROM_SUP_A_MAX_HOPS_2",
    "EXPECTED_SUBGRAPH_EDGE_KEYS_FROM_SUP_A_MAX_HOPS_1",
    "EXPECTED_SUBGRAPH_NODE_IDS_FROM_SUP_A_MAX_HOPS_1",
    "EXPECTED_UNRESOLVED_MENTIONS",
    "build_entity_stream",
    "build_event_signals",
    "build_orders",
    "build_shipments",
    "build_suppliers",
]
