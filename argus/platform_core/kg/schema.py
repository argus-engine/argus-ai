# SPDX-License-Identifier: Apache-2.0
"""Typed schema for the knowledge graph layer.

Node and edge types are domain-aware (Supplier / Product / Region / etc.)
but engine-agnostic — both backends in this package produce the same
:class:`KGNode` and :class:`KGEdge` instances regardless of where the data
is stored.

Each entity carries a stable, human-readable identifier of the form
``"{node_type}:{source_key}"`` (e.g. ``"supplier:SUP-001"`` or
``"region:APAC"``). Stable IDs are what make ingestion idempotent —
re-running the same source produces the same identifiers, so upserts
converge instead of accumulating duplicates. Edge IDs follow the
companion shape ``"{source_id}-{EDGE_TYPE}->{target_id}"`` so they
read naturally in logs and the Neo4j browser.

Schema design notes:

- :class:`NodeType` and :class:`EdgeType` are :class:`str` enums so they
  serialise cleanly to JSON and to Cypher labels / relationship types
  without custom encoders.
- :class:`KGNode` and :class:`KGEdge` are frozen, ``extra="forbid"`` —
  the same immutability and strict-shape contract used elsewhere in
  ``platform_core``.
- ``properties`` is an open ``dict[str, Any]``: backends carry whatever
  the adapter chose to project. Validation of property contents is the
  adapter's responsibility, not this module's.
- ``source_refs`` is a tuple of ``RawRecord.provenance`` strings —
  the audit trail from raw record to graph entity. Multiple refs are
  expected when the same node is upserted from several sources.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Typed node and edge labels
# ---------------------------------------------------------------------------


class NodeType(StrEnum):
    """Typed node labels carried in the knowledge graph.

    The seven types span the supply-chain domain: physical actors
    (``SUPPLIER``, ``CUSTOMER``), the goods that move between them
    (``PRODUCT``, ``ORDER``, ``SHIPMENT``), the geography they operate in
    (``REGION``), and the external signals that perturb them
    (``EVENT_SIGNAL``).

    ``PRODUCT``, ``REGION`` and ``CUSTOMER`` are synthesised from scalar
    fields on the source entities (``Order.product_id``,
    ``Order.destination_region``, ``Order.customer_id``) — they are first-class
    nodes here because the cascading-risk and subgraph queries that land in
    later Phase-2 tasks need them as queryable entities, not as opaque
    properties.
    """

    SUPPLIER = "supplier"
    PRODUCT = "product"
    REGION = "region"
    ORDER = "order"
    SHIPMENT = "shipment"
    CUSTOMER = "customer"
    EVENT_SIGNAL = "event_signal"


class EdgeType(StrEnum):
    """Typed relationship labels carried in the knowledge graph.

    The relationships the supply-chain adapter projects from the four
    source entities are:

    +------------------+----------------------------------------------------+
    | ``HAS_SUPPLIER`` | ``Order`` → ``Supplier``                           |
    +------------------+----------------------------------------------------+
    | ``PLACED_BY``    | ``Order`` → ``Customer``                           |
    +------------------+----------------------------------------------------+
    | ``OF_PRODUCT``   | ``Order`` → ``Product``                            |
    +------------------+----------------------------------------------------+
    | ``FULFILS_ORDER``| ``Shipment`` → ``Order``                           |
    +------------------+----------------------------------------------------+
    | ``SUPPLIED_BY``  | ``Shipment`` → ``Supplier``                        |
    +------------------+----------------------------------------------------+
    | ``SHIPS_TO``     | ``Shipment`` → ``Region`` (destination)            |
    +------------------+----------------------------------------------------+
    | ``LOCATED_IN``   | ``Supplier`` / ``Customer`` → ``Region``           |
    +------------------+----------------------------------------------------+
    | ``DEPENDS_ON``   | ``Product`` → ``Supplier`` (transitive BoM seam)   |
    +------------------+----------------------------------------------------+
    | ``AFFECTS``      | ``EventSignal`` → any node (cascading-risk seed)   |
    +------------------+----------------------------------------------------+
    | ``MENTIONS``     | ``EventSignal`` → any node (resolved mention)      |
    +------------------+----------------------------------------------------+

    Cypher convention is uppercase relationship types; the enum values
    match so the same identifier flows from Python through the parameterised
    Cypher into the Neo4j browser unchanged.
    """

    HAS_SUPPLIER = "HAS_SUPPLIER"
    PLACED_BY = "PLACED_BY"
    OF_PRODUCT = "OF_PRODUCT"
    FULFILS_ORDER = "FULFILS_ORDER"
    SUPPLIED_BY = "SUPPLIED_BY"
    SHIPS_TO = "SHIPS_TO"
    LOCATED_IN = "LOCATED_IN"
    DEPENDS_ON = "DEPENDS_ON"
    AFFECTS = "AFFECTS"
    MENTIONS = "MENTIONS"


# ---------------------------------------------------------------------------
# Stable-identifier helpers
# ---------------------------------------------------------------------------


def make_node_id(node_type: NodeType, source_key: str) -> str:
    """Build a stable, debuggable node ID from a type and source key.

    Returns ``f"{node_type.value}:{source_key}"`` — for example
    ``make_node_id(NodeType.SUPPLIER, "SUP-001") == "supplier:SUP-001"``.

    Centralised so adapters and tests agree on the format; do not
    hand-construct node IDs anywhere else. Re-running ingestion on the
    same source key produces the same ID, which is what makes the upsert
    pipeline idempotent.

    Args:
        node_type: The :class:`NodeType` this identifier denotes.
        source_key: The upstream identifier (e.g. ``Supplier.supplier_id``).

    Raises:
        ValueError: If ``source_key`` is empty.
    """
    if not source_key:
        raise ValueError("source_key must be non-empty")
    return f"{node_type.value}:{source_key}"


def make_edge_id(source_id: str, edge_type: EdgeType, target_id: str) -> str:
    """Build a stable edge ID from its endpoints and relationship type.

    Returns ``f"{source_id}-{edge_type.value}->{target_id}"`` — for example
    ``"order:LINE-42-HAS_SUPPLIER->supplier:SUP-001"``. The arrow notation
    matches how Cypher patterns read aloud, so an edge ID and the Cypher
    query that returns it look the same.

    Args:
        source_id: The ``id`` of the edge's source :class:`KGNode`.
        edge_type: The :class:`EdgeType` for this relationship.
        target_id: The ``id`` of the edge's target :class:`KGNode`.

    Raises:
        ValueError: If either endpoint ID is empty.
    """
    if not source_id or not target_id:
        raise ValueError("source_id and target_id must be non-empty")
    return f"{source_id}-{edge_type.value}->{target_id}"


# ---------------------------------------------------------------------------
# KGNode and KGEdge
# ---------------------------------------------------------------------------


class KGNode(BaseModel):
    """A typed node in the knowledge graph.

    Construct ``id`` via :func:`make_node_id` so the stable-ID format is
    consistent. ``properties`` carries whatever scalar fields the adapter
    chose to project onto the node — fields that should themselves be
    nodes (e.g. ``Order.supplier_id``) belong in edges, not here.
    """

    model_config = _FROZEN

    id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier; typically produced by make_node_id().",
    )
    type: NodeType
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Scalar fields projected onto the node by the adapter.",
    )
    source_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Provenance trail — RawRecord.provenance strings.",
    )


class KGEdge(BaseModel):
    """A typed, directed edge in the knowledge graph.

    Construct ``id`` via :func:`make_edge_id`. Edges are directed; the
    adapter chooses the orientation that makes downstream queries natural
    (e.g. ``Order -HAS_SUPPLIER-> Supplier`` so that traversing outward
    from an order reaches its supplier).
    """

    model_config = _FROZEN

    id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier; typically produced by make_edge_id().",
    )
    source_id: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    type: EdgeType
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional scalar attributes (weights, timestamps, ...).",
    )
    source_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Provenance trail — RawRecord.provenance strings.",
    )


__all__ = [
    "EdgeType",
    "KGEdge",
    "KGNode",
    "NodeType",
    "make_edge_id",
    "make_node_id",
]
