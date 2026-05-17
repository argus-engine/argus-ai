# SPDX-License-Identifier: Apache-2.0
"""In-process :class:`KGBackend` implementation backed by NetworkX.

Used for unit tests, offline development, and any deployment where a
real graph database is overkill. The implementation maps each
:class:`KGNode` onto a NetworkX node attribute and each :class:`KGEdge`
onto a multi-edge attribute in a :class:`networkx.MultiDiGraph` — multi
because a single pair of nodes can be connected by several typed
relationships (e.g. a shipment-to-region pair carrying both ``SHIPS_TO``
and a hypothetical ``ROUTES_THROUGH``), directed because edges have a
canonical orientation chosen by the adapter.

**Traversal direction.** Knowledge-graph edges encode ownership /
foreign-key direction (``Order -HAS_SUPPLIER-> Supplier``), not the
direction in which risk propagates. A disruption at a Supplier reaches
its Orders by traversing *incoming* ``HAS_SUPPLIER`` edges. The BFS
underneath :meth:`cascading_risk` and :meth:`subgraph` therefore walks
the graph **bidirectionally** — outgoing and incoming edges are both
candidates at each hop — while :meth:`neighbors` and
:meth:`shortest_path` remain direction-aware because their semantics
demand it. :meth:`shortest_path` uses :func:`networkx.shortest_path` with
a hard length cap to avoid pathological behaviour on dense graphs.

**Determinism.** BFS sorts candidate edges by ``edge.id`` before
expansion, and :meth:`cascading_risk` sorts its output by
``(hops, target_id)``. The same input graph and arguments therefore
produce byte-identical results across runs — important for tests and
for the integration-test parity check between this backend and the
Neo4j one in Task #3.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence

import networkx as nx

from argus.platform_core.kg.base import (
    Direction,
    KGBackendConfig,
    RiskPath,
    Subgraph,
)
from argus.platform_core.kg.schema import EdgeType, KGEdge, KGNode

_NODE_ATTR = "node"
"""NetworkX node attribute holding the :class:`KGNode` payload."""

_EDGE_ATTR = "edge"
"""NetworkX edge attribute holding the :class:`KGEdge` payload."""

_SHORTEST_PATH_MAX_EDGES = 20
"""Cap on the number of edges :meth:`shortest_path` will traverse."""


class NetworkXBackend:
    """In-process knowledge-graph backend backed by :class:`networkx.MultiDiGraph`.

    Constructed from a :class:`KGBackendConfig`; the ``neo4j_*`` fields
    are ignored. Satisfies the :class:`KGBackend` Protocol via duck
    typing (no inheritance — keeping the implementation testable without
    the Protocol's ABC machinery).
    """

    __slots__ = ("_config", "_connected", "_graph")

    def __init__(self, config: KGBackendConfig) -> None:
        self._config = config
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._connected = False

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    @property
    def config(self) -> KGBackendConfig:
        """The configuration passed at construction time."""
        return self._config

    def connect(self) -> None:
        """No-op for the in-process backend; the graph exists once constructed."""
        self._connected = True

    def disconnect(self) -> None:
        """No-op for the in-process backend; safe to call repeatedly."""
        self._connected = False

    # ---------------------------------------------------------------------
    # Upsert
    # ---------------------------------------------------------------------

    def upsert_node(self, node: KGNode) -> None:
        """Insert or update a node, applying the merge semantics from the Protocol."""
        existing = self._get_stored_node(node.id)
        if existing is not None and existing.type is not node.type:
            raise ValueError(
                f"node id {node.id!r} already exists with type "
                f"{existing.type.value!r}; refusing to overwrite with "
                f"type {node.type.value!r}"
            )
        merged = _merge_node(existing, node)
        self._graph.add_node(merged.id, **{_NODE_ATTR: merged})

    def upsert_edge(self, edge: KGEdge) -> None:
        """Insert or update an edge, applying the merge semantics from the Protocol."""
        existing = self._get_stored_edge(edge)
        if existing is not None and existing.type is not edge.type:
            raise ValueError(
                f"edge id {edge.id!r} already exists with type "
                f"{existing.type.value!r}; refusing to overwrite with "
                f"type {edge.type.value!r}"
            )
        merged = _merge_edge(existing, edge)
        # MultiDiGraph implicitly creates endpoint nodes if absent — the
        # Protocol tolerates dangling references, so we let that happen.
        self._graph.add_edge(
            merged.source_id,
            merged.target_id,
            key=merged.id,
            **{_EDGE_ATTR: merged},
        )

    # ---------------------------------------------------------------------
    # Read
    # ---------------------------------------------------------------------

    def get_node(self, node_id: str) -> KGNode | None:
        """Return the stored :class:`KGNode`, or ``None`` if unknown or dangling."""
        return self._get_stored_node(node_id)

    def neighbors(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        direction: Direction = "out",
    ) -> Sequence[KGNode]:
        """Return the immediate neighbours of ``node_id``.

        Honours both ``direction`` and ``edge_types``; returns an empty
        tuple if the node is unknown. Dangling endpoint nodes (those
        referenced by an edge but never upserted) are skipped — the
        caller asked for KGNodes, not anonymous graph keys.
        """
        if node_id not in self._graph:
            return ()
        wanted = _coerce_edge_types(edge_types)
        seen: dict[str, KGNode] = {}
        for neighbor_id, edge in self._adjacent(node_id, direction):
            if wanted is not None and edge.type not in wanted:
                continue
            payload = self._get_stored_node(neighbor_id)
            if payload is None:
                continue
            seen.setdefault(neighbor_id, payload)
        return tuple(sorted(seen.values(), key=lambda n: n.id))

    def subgraph(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> Subgraph:
        """Return the induced subgraph reachable from ``seed_ids`` within ``max_hops``.

        BFS is bidirectional. The returned :class:`Subgraph` contains
        every node reached that has a stored :class:`KGNode` payload and
        every edge between any two collected nodes whose ``type`` passes
        the ``edge_types`` filter — i.e. the induced subgraph, not just
        the spanning-tree edges traversed during BFS.
        """
        wanted = _coerce_edge_types(edge_types)
        reached: set[str] = set()
        for seed in seed_ids:
            if seed not in self._graph:
                continue
            reached.add(seed)
            for neighbor_id, _ in self._bfs(seed, max_hops, wanted):
                reached.add(neighbor_id)

        collected_nodes: dict[str, KGNode] = {}
        for nid in reached:
            payload = self._get_stored_node(nid)
            if payload is not None:
                collected_nodes[nid] = payload

        valid_ids = collected_nodes.keys()
        collected_edges: dict[str, KGEdge] = {}
        for source_id, target_id, _key, data in self._graph.edges(keys=True, data=True):
            if source_id not in valid_ids or target_id not in valid_ids:
                continue
            edge = _edge_from_data(data)
            if edge is None:
                continue
            if wanted is not None and edge.type not in wanted:
                continue
            collected_edges[edge.id] = edge

        return Subgraph(
            nodes=tuple(sorted(collected_nodes.values(), key=lambda n: n.id)),
            edges=tuple(sorted(collected_edges.values(), key=lambda e: e.id)),
        )

    def cascading_risk(
        self,
        start_id: str,
        *,
        max_hops: int = 3,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> Sequence[RiskPath]:
        """Return downstream-impact paths from ``start_id`` within ``max_hops``.

        BFS is bidirectional — edges encode FK direction, not impact
        flow, so risk propagates both ways. The returned sequence is
        sorted by ``(hops, target_id)`` for deterministic output.
        Returns an empty sequence when ``start_id`` is unknown.
        """
        wanted = _coerce_edge_types(edge_types)
        paths: list[RiskPath] = []
        for target_id, edge_path in self._bfs(start_id, max_hops, wanted):
            paths.append(
                RiskPath(
                    start_id=start_id,
                    target_id=target_id,
                    path=tuple(edge_path),
                    hops=len(edge_path),
                )
            )
        paths.sort(key=lambda p: (p.hops, p.target_id))
        return paths

    def shortest_path(self, source_id: str, target_id: str) -> Sequence[KGNode] | None:
        """Return the shortest directed node sequence, or ``None`` if absent.

        Uses :func:`networkx.shortest_path` with a hard cap of
        :data:`_SHORTEST_PATH_MAX_EDGES` edges; longer paths return
        ``None`` rather than risking a runaway traversal on a dense
        graph. If any intermediate node is a dangling endpoint (no
        stored :class:`KGNode` payload), the path is rejected because
        the caller expects a sequence of materialised nodes.
        """
        if source_id not in self._graph or target_id not in self._graph:
            return None
        try:
            node_ids: list[str] = nx.shortest_path(self._graph, source=source_id, target=target_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        if len(node_ids) - 1 > _SHORTEST_PATH_MAX_EDGES:
            return None
        result: list[KGNode] = []
        for nid in node_ids:
            payload = self._get_stored_node(nid)
            if payload is None:
                return None
            result.append(payload)
        return tuple(result)

    def clear(self) -> None:
        """Remove every node and edge."""
        self._graph.clear()

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _get_stored_node(self, node_id: str) -> KGNode | None:
        if node_id not in self._graph:
            return None
        data = self._graph.nodes[node_id]
        payload = data.get(_NODE_ATTR)
        if isinstance(payload, KGNode):
            return payload
        return None

    def _get_stored_edge(self, edge: KGEdge) -> KGEdge | None:
        if not self._graph.has_edge(edge.source_id, edge.target_id, key=edge.id):
            return None
        data = self._graph.get_edge_data(edge.source_id, edge.target_id, key=edge.id)
        return _edge_from_data(data)

    def _adjacent(self, node_id: str, direction: Direction) -> Iterator[tuple[str, KGEdge]]:
        """Yield ``(neighbor_id, edge)`` for each adjacent edge honoring ``direction``.

        Sorted by ``edge.id`` for deterministic traversal so that any
        ordering-sensitive query (e.g. tie-breaking on shortest-path or
        BFS hop frontiers) is reproducible across runs.
        """
        candidates: list[tuple[str, KGEdge]] = []
        if direction in ("out", "both"):
            for _u, v, _k, data in self._graph.out_edges(node_id, keys=True, data=True):
                edge = _edge_from_data(data)
                if edge is not None:
                    candidates.append((v, edge))
        if direction in ("in", "both"):
            for u, _v, _k, data in self._graph.in_edges(node_id, keys=True, data=True):
                edge = _edge_from_data(data)
                if edge is not None:
                    candidates.append((u, edge))
        candidates.sort(key=lambda pair: pair[1].id)
        yield from candidates

    def _bfs(
        self,
        start: str,
        max_hops: int,
        edge_types: frozenset[EdgeType] | None,
    ) -> Iterator[tuple[str, list[KGEdge]]]:
        """Yield ``(node_id, edge_path)`` for every node reached within ``max_hops``.

        Bidirectional — each frontier expands across both outgoing and
        incoming edges of the current node. ``start`` is never yielded.
        Visited nodes are skipped so each target gets the shortest path
        found (one path per node, BFS semantics).
        """
        if start not in self._graph or max_hops <= 0:
            return
        visited: set[str] = {start}
        frontier: list[tuple[str, list[KGEdge]]] = [(start, [])]
        for _ in range(max_hops):
            next_frontier: list[tuple[str, list[KGEdge]]] = []
            for current, path in frontier:
                for neighbor_id, edge in self._adjacent(current, "both"):
                    if edge_types is not None and edge.type not in edge_types:
                        continue
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)
                    new_path = [*path, edge]
                    next_frontier.append((neighbor_id, new_path))
                    yield neighbor_id, new_path
            if not next_frontier:
                break
            frontier = next_frontier


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _coerce_edge_types(
    edge_types: Iterable[EdgeType] | None,
) -> frozenset[EdgeType] | None:
    """Return a frozenset for fast membership, or ``None`` when no filter."""
    if edge_types is None:
        return None
    return frozenset(edge_types)


def _edge_from_data(data: object) -> KGEdge | None:
    """Extract the :class:`KGEdge` payload from a NetworkX edge-data dict."""
    if isinstance(data, dict):
        candidate = data.get(_EDGE_ATTR)
        if isinstance(candidate, KGEdge):
            return candidate
    return None


def _merge_node(existing: KGNode | None, incoming: KGNode) -> KGNode:
    """Apply the upsert_node merge semantics defined on the Protocol."""
    if existing is None:
        return incoming
    merged_properties = {**existing.properties, **incoming.properties}
    merged_source_refs = _union_preserving_order(existing.source_refs, incoming.source_refs)
    return KGNode(
        id=incoming.id,
        type=incoming.type,
        properties=merged_properties,
        source_refs=merged_source_refs,
    )


def _merge_edge(existing: KGEdge | None, incoming: KGEdge) -> KGEdge:
    """Apply the upsert_edge merge semantics defined on the Protocol."""
    if existing is None:
        return incoming
    merged_properties = {**existing.properties, **incoming.properties}
    merged_source_refs = _union_preserving_order(existing.source_refs, incoming.source_refs)
    return KGEdge(
        id=incoming.id,
        source_id=incoming.source_id,
        target_id=incoming.target_id,
        type=incoming.type,
        properties=merged_properties,
        source_refs=merged_source_refs,
    )


def _union_preserving_order(
    existing: tuple[str, ...], incoming: tuple[str, ...]
) -> tuple[str, ...]:
    """Union two tuples, deduplicating while preserving first-seen order."""
    return tuple(dict.fromkeys((*existing, *incoming)))


__all__ = ["NetworkXBackend"]
