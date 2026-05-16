# SPDX-License-Identifier: Apache-2.0
"""Base contracts for the knowledge graph layer.

This module defines the storage-engine seam: the :class:`KGBackend` Protocol
that both backends in this package (:class:`NetworkXBackend` in Task #2 and
:class:`Neo4jBackend` in Task #3) implement. Caller code depends on the
Protocol — never on a concrete backend — so swapping engines is a
configuration change, not an import change.

Design notes:

- The Protocol is :func:`~typing.runtime_checkable` so test stubs can
  satisfy it without inheriting from a base class.
- Result wrappers (:class:`Subgraph`, :class:`RiskPath`) are frozen Pydantic
  models so query results carry the same immutability guarantees the
  ingestion layer's records do.
- Backend configuration lives in a single :class:`KGBackendConfig` even
  though the NetworkX backend ignores most fields. A union shape keeps the
  factory (Task #2) free of per-backend ``isinstance`` branching when
  resolving config from ``pydantic-settings``.
- ``connect`` / ``disconnect`` are explicit. A context-manager Protocol
  layered on top can land later if call sites need it; nothing in Phase 2
  requires it yet, and adding it now would force every test stub to
  implement ``__enter__`` and ``__exit__``.

Idempotency contract (binding on every implementation):

    ``upsert_node`` and ``upsert_edge`` MUST be safe to call repeatedly
    with the same input. Re-ingesting unchanged source data is the
    expected case, not an error condition.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from argus.platform_core.kg.schema import EdgeType, KGEdge, KGNode

_FROZEN = ConfigDict(frozen=True, extra="forbid")


Direction = Literal["in", "out", "both"]
"""Edge-traversal direction for neighbourhood and path queries."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class KGBackendConfig(BaseModel):
    """Configuration shared across :class:`KGBackend` implementations.

    Fields that are specific to one backend (the ``neo4j_*`` group) are
    optional so the in-process :class:`NetworkXBackend` can be constructed
    from the same config object without populating Neo4j-only knobs.

    Resolution order (mirrors the three-tier pattern used elsewhere in
    ``platform_core``): explicit constructor argument → environment
    variable → ``configs/default.yaml`` value.
    """

    model_config = _FROZEN

    name: str = Field(
        ...,
        min_length=1,
        description="Identifier used in logs, metrics, and error messages.",
    )
    neo4j_uri: str | None = Field(
        default=None,
        description="Bolt URI for the Neo4j backend (e.g. bolt://localhost:7687).",
    )
    neo4j_user: str | None = Field(
        default=None,
        description="Neo4j username; omit when auth is disabled (local compose).",
    )
    neo4j_password: SecretStr | None = Field(
        default=None,
        description="Neo4j password; wrapped in SecretStr to keep it out of repr().",
    )
    neo4j_database: str = Field(
        default="neo4j",
        min_length=1,
        description="Target Neo4j database name (Neo4j 4+ multi-db).",
    )


# ---------------------------------------------------------------------------
# Query result wrappers
# ---------------------------------------------------------------------------


class Subgraph(BaseModel):
    """A typed result returned by :meth:`KGBackend.subgraph` and peers.

    Carries the nodes and edges that satisfied the query. The caller can
    convert to a NetworkX graph or a Cypher result row, but the wire shape
    is always this — engine-agnostic and JSON-serialisable.
    """

    model_config = _FROZEN

    nodes: tuple[KGNode, ...] = Field(default_factory=tuple)
    edges: tuple[KGEdge, ...] = Field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.nodes)

    def __bool__(self) -> bool:
        return bool(self.nodes)


class RiskPath(BaseModel):
    """One downstream-impact path returned by :meth:`KGBackend.cascading_risk`.

    ``path`` is the ordered list of edges traversed from ``start_id`` to
    ``target_id``. ``hops`` equals ``len(path)`` and is materialised
    explicitly for cheap sorting and filtering by depth.
    """

    model_config = _FROZEN

    start_id: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    path: tuple[KGEdge, ...] = Field(
        ...,
        description="Ordered edges from start to target; len(path) == hops.",
    )
    hops: int = Field(..., ge=1)


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class KGBackend(Protocol):
    """The storage-engine seam for the Argus knowledge graph.

    Implementations land in later Phase-2 tasks: :class:`NetworkXBackend`
    (Task #2, in-process, used for unit tests and offline dev),
    :class:`Neo4jBackend` (Task #3, talks to the docker-compose service
    or a testcontainers Neo4j via the official driver, APOC required).

    The Protocol is intentionally narrow. Methods cover what the rest of
    the platform needs in Phases 2-4: idempotent ingest, point lookups,
    neighbourhood walks, subgraph extraction, cascading-risk traversal,
    and full clear-out for tests.

    Every method is synchronous. An async surface is not in scope for
    Phase 2; if a backend later needs it, it lands as sibling ``a*``
    methods rather than replacing the sync ones.
    """

    def connect(self) -> None:
        """Open the underlying connection (driver, in-memory graph, ...).

        Safe to call repeatedly; subsequent calls on an already-connected
        backend are no-ops.
        """

    def disconnect(self) -> None:
        """Release the underlying connection. Idempotent."""

    def upsert_node(self, node: KGNode) -> None:
        """Insert or update a node, keyed by ``node.id``.

        Replacing an existing node merges ``properties`` and unions
        ``source_refs`` — the implementations document the exact merge
        semantics. Must be idempotent: repeated calls with the same input
        leave the graph in the same state.
        """

    def upsert_edge(self, edge: KGEdge) -> None:
        """Insert or update an edge, keyed by ``edge.id``.

        Edges referencing nodes that have not been upserted yet are
        tolerated — real data streams arrive out of order, and waiting
        for referential integrity would block ingestion. Both backends
        in this phase resolve dangling references lazily on read.
        """

    def get_node(self, node_id: str) -> KGNode | None:
        """Return the node with this ``id``, or ``None`` if absent."""

    def neighbors(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        direction: Direction = "out",
    ) -> Sequence[KGNode]:
        """Return the immediate neighbours of ``node_id``.

        ``edge_types`` filters which relationships are traversed; ``None``
        means all types. ``direction`` selects outgoing, incoming, or
        both. Returns an empty sequence if ``node_id`` is absent — that
        is not an error, because data may arrive out of order.
        """

    def subgraph(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> Subgraph:
        """Extract the subgraph reachable from ``seed_ids`` within ``max_hops``.

        The primitive used by the Phase 4 RAG layer: given the entities
        mentioned in a query, return the typed neighbourhood the LLM
        should be grounded against. Seeds that do not exist are silently
        skipped — the returned subgraph reflects what was found.
        """

    def cascading_risk(
        self,
        start_id: str,
        *,
        max_hops: int = 3,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> Sequence[RiskPath]:
        """Return downstream-impact paths originating at ``start_id``.

        Used to answer questions like *"if supplier X is disrupted,
        which orders, products, customers, and regions are affected and
        by how many hops?"*. Each returned :class:`RiskPath` is one
        ordered chain of edges; depth-bounded by ``max_hops``.
        """

    def shortest_path(self, source_id: str, target_id: str) -> Sequence[KGNode] | None:
        """Return the shortest node sequence from ``source_id`` to ``target_id``.

        Returns ``None`` if no path exists. Length-tie-breaking is
        backend-specific; callers needing deterministic ordering should
        post-process.
        """

    def clear(self) -> None:
        """Remove every node and edge.

        Used by tests between cases (and by operational tools); never
        called by production ingestion paths.
        """


__all__ = [
    "Direction",
    "KGBackend",
    "KGBackendConfig",
    "RiskPath",
    "Subgraph",
]
