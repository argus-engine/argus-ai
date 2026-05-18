# SPDX-License-Identifier: Apache-2.0
"""Idempotent ingestion of domain entities into a :class:`KGBackend`.

The builder is a thin orchestrator: it iterates entities, asks a
domain-specific :class:`KGAdapter` to project each one into nodes and
edges, and forwards the result to the backend's upsert methods.

Two contracts make this composition safe:

1. **Idempotency** is enforced by the backend (its ``upsert_*`` methods
   converge on repeat calls). The builder simply forwards.
2. **Order tolerance** — adapters yield nodes for an entity before edges,
   so backends that prefer endpoints-first see them that way. Edges that
   reference yet-unseen nodes are still tolerated by both backends in
   this phase, because real data streams arrive out of order across
   entities (a shipment referencing an order that hasn't been ingested
   yet, for example).

The adapter Protocol is generic in the entity type. The supply-chain
adapter (Task #4) is parameterised over the union of the four
supply-chain entities; a future pack would parameterise over its own.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from argus.platform_core.kg.base import KGBackend
from argus.platform_core.kg.schema import KGEdge, KGNode

EntityT = TypeVar("EntityT")
# Contravariant variant for the Protocol below: the entity flows only into
# adapter methods, so an adapter for a more general entity type is a valid
# substitute for one that handles a narrower type.
_EntityT_contra = TypeVar("_EntityT_contra", contravariant=True)


# ---------------------------------------------------------------------------
# Adapter Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class KGAdapter(Protocol[_EntityT_contra]):
    """Maps a domain entity to KG nodes and edges.

    Each domain pack ships its own adapter. The implementation is pure:
    given an entity, it returns iterables of nodes and edges, performing
    any derived-node construction (e.g. a :class:`KGNode` of type
    ``REGION`` synthesised from ``Supplier.region``) and any opaque-string
    resolution it can do statically.

    Adapters should yield deterministically — running ``to_nodes`` and
    ``to_edges`` on the same entity twice must produce equal sequences,
    which is what makes the builder idempotent in turn.
    """

    def to_nodes(self, entity: _EntityT_contra) -> Iterable[KGNode]:
        """Project ``entity`` into the nodes it implies."""

    def to_edges(self, entity: _EntityT_contra) -> Iterable[KGEdge]:
        """Project ``entity`` into the edges it implies."""

    def counters(self) -> Mapping[str, int]:
        """Return zero-or-more named counters accumulated during ingestion.

        Called once by :meth:`KGBuilder.ingest` after the entity loop
        completes; the returned mapping is copied into
        :attr:`IngestionReport.adapter_counters`. Stateless adapters
        return an empty mapping. Pack-specific adapters expose counts
        that have no platform-core meaning here (for example, the
        supply-chain adapter reports ``unresolved_mentions`` for
        ``EventSignal.entities_mentioned`` strings that did not match
        any known node).
        """


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class IngestionReport(BaseModel):
    """Summary of one :meth:`KGBuilder.ingest` invocation.

    Returned to the caller so the CLI, the API layer, and future
    observability hooks have a typed surface to read counts and timing
    from without scraping logs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes_seen: int = Field(
        ...,
        ge=0,
        description="Total node upsert calls made (may double-count when an "
        "entity emits the same node twice; backends dedupe on id).",
    )
    edges_seen: int = Field(..., ge=0, description="Total edge upsert calls made.")
    duration_ms: int = Field(..., ge=0, description="Wall-clock duration of ingest().")
    started_at: datetime = Field(
        ...,
        description="UTC, tz-aware timestamp captured at the start of ingest().",
    )
    adapter_counters: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Per-adapter named counters collected after ingestion completes "
            "(e.g. unresolved-entity counts from a pack-specific adapter). "
            "Empty for stateless adapters."
        ),
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class KGBuilder(Generic[EntityT]):
    """Orchestrates idempotent ingestion of domain entities into a backend.

    Construction takes a :class:`KGBackend` and a :class:`KGAdapter` for
    the entity type being ingested. ``ingest`` then consumes any iterable
    of entities — typically a stream from the ingestion layer's
    connectors — and projects each one into the backend.

    The builder does not open or close the backend connection. Lifecycle
    is the caller's responsibility (or a future context-manager wrapper);
    keeping the builder agnostic lets it be reused across batches without
    reconnect overhead.
    """

    __slots__ = ("_adapter", "_backend")

    def __init__(self, backend: KGBackend, adapter: KGAdapter[EntityT]) -> None:
        self._backend = backend
        self._adapter = adapter

    def ingest(self, entities: Iterable[EntityT]) -> IngestionReport:
        """Project every entity through the adapter and upsert into the backend.

        Streaming: ``entities`` is consumed lazily and never fully
        materialised. Per entity, nodes are upserted before edges so
        backends that prefer endpoints-first see them that way.
        """
        started_at = datetime.now(UTC)
        start = time.perf_counter()
        nodes_seen = 0
        edges_seen = 0
        for entity in entities:
            for node in self._adapter.to_nodes(entity):
                self._backend.upsert_node(node)
                nodes_seen += 1
            for edge in self._adapter.to_edges(entity):
                self._backend.upsert_edge(edge)
                edges_seen += 1
        duration_ms = int((time.perf_counter() - start) * 1000)
        return IngestionReport(
            nodes_seen=nodes_seen,
            edges_seen=edges_seen,
            duration_ms=duration_ms,
            started_at=started_at,
            adapter_counters=dict(self._adapter.counters()),
        )


__all__ = [
    "IngestionReport",
    "KGAdapter",
    "KGBuilder",
]
