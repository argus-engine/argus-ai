# SPDX-License-Identifier: Apache-2.0
"""Neo4j backend for the knowledge graph.

This module file can be imported on a base install — only constructing
a :class:`Neo4jBackend` instance triggers the ``neo4j`` driver
dependency. Install the heavier dependencies with
``pip install argus-risk[kg]`` to enable this backend; until then,
:func:`make_backend` returns the in-process
:class:`~argus.platform_core.kg.networkx_backend.NetworkXBackend`.

Storage model
-------------

- Every node carries the ``:KGNode`` label and a stable ``id``
  property. A uniqueness constraint on ``id`` enforces idempotency at
  the storage layer; the in-Python type-mismatch check then provides
  the higher-level "same id with a different type is a bug" semantics
  documented on :class:`~argus.platform_core.kg.base.KGBackend`.
- Each relationship's Cypher type matches the corresponding
  :class:`~argus.platform_core.kg.schema.EdgeType` value — patterns
  like ``(a)-[:HAS_SUPPLIER]->(b)`` and the
  :func:`apoc.path.expandConfig` ``relationshipFilter`` argument both
  read naturally. Dynamic-type creation goes through
  :func:`apoc.merge.relationship`.
- Schema-reserved property keys on nodes are ``id``, ``type``,
  ``source_refs``; on relationships, ``id`` and ``source_refs``. User
  ``properties`` are spread onto the node / relationship directly via
  ``SET n += $props``.

Cypher safety
-------------

All values flow through ``$param`` substitution — no user-controlled
value is ever interpolated into a query string. Internal Literals
(traversal direction, edge-type filter strings) are interpolated, but
those come from the typed Python surface, not from the caller.

Merge semantics
---------------

The merge contract from :class:`KGBackend` is implemented with
read-modify-write in Python (type-mismatch check, source-refs
ordered union via :func:`dict.fromkeys`) and a single ``MERGE ... SET``
in Cypher. Property merging uses ``SET n += $props`` which overrides
existing keys with incoming values and preserves untouched keys —
exactly the Protocol contract. ``apoc.coll.toSet`` is deliberately
*not* used for source-refs because it does not preserve first-seen
order, which the Protocol guarantees.

Bidirectional traversal
-----------------------

KG edges encode FK direction, not impact-propagation direction.
:meth:`cascading_risk` and :meth:`subgraph` therefore call APOC with
an empty / "type-only" ``relationshipFilter`` so the traversal walks
edges in either direction. This matches
:class:`NetworkXBackend`'s BFS semantics so the parity tests pass.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from argus.platform_core.kg.base import (
    Direction,
    KGBackendConfig,
    RiskPath,
    Subgraph,
)
from argus.platform_core.kg.schema import EdgeType, KGEdge, KGNode, NodeType

_SHORTEST_PATH_MAX_EDGES = 20
"""Hard cap on path length for :meth:`Neo4jBackend.shortest_path`."""

_RESERVED_NODE_KEYS = frozenset({"id", "type", "source_refs"})
"""Property keys that carry schema meaning on a node and must not be overwritten."""

_RESERVED_EDGE_KEYS = frozenset({"id", "source_refs"})
"""Property keys that carry schema meaning on a relationship."""

_CONNECT_TIMEOUT_SECONDS = 5.0
"""Driver connection-acquisition timeout. Bounded so a bad URI fails fast."""


class Neo4jBackend:
    """Neo4j-backed knowledge-graph implementation.

    The constructor lazy-imports the ``neo4j`` driver so this module
    remains importable on a base install. A clear :class:`ImportError`
    is raised when the driver is missing.
    """

    def __init__(self, config: KGBackendConfig) -> None:
        try:
            from neo4j import GraphDatabase, exceptions as neo4j_exceptions
        except ImportError as exc:  # pragma: no cover - exercised in CI bare install
            raise ImportError(
                "Neo4j backend requires the neo4j driver. "
                "Install with `pip install argus-risk[kg]`."
            ) from exc

        if not config.neo4j_uri:
            raise ValueError("Neo4jBackend requires neo4j_uri to be set on the KGBackendConfig")

        self._config = config
        self._uri = config.neo4j_uri
        self._user = config.neo4j_user
        self._password: str | None = (
            config.neo4j_password.get_secret_value() if config.neo4j_password is not None else None
        )
        self._database = config.neo4j_database
        self._graph_database = GraphDatabase
        self._exceptions = neo4j_exceptions
        self._driver: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def config(self) -> KGBackendConfig:
        return self._config

    def connect(self) -> None:
        """Open the driver, verify APOC availability, and ensure constraints exist.

        Idempotent — calling ``connect`` on an already-connected backend
        is a no-op. Raises :class:`RuntimeError` if APOC is missing,
        with a message pointing at the supported install paths.
        """
        if self._driver is not None:
            return

        auth: tuple[str, str] | None = None
        if self._user is not None and self._password is not None:
            auth = (self._user, self._password)

        self._driver = self._graph_database.driver(
            self._uri,
            auth=auth,
            connection_timeout=_CONNECT_TIMEOUT_SECONDS,
        )
        try:
            self._driver.verify_connectivity()
        except Exception:
            self._driver.close()
            self._driver = None
            raise

        self._verify_apoc_available()
        self._ensure_constraints()

    def disconnect(self) -> None:
        """Close the driver. Idempotent."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_node(self, node: KGNode) -> None:
        """Insert or update a node, applying the merge semantics from the Protocol."""
        self._require_connected()
        safe_props = {k: v for k, v in node.properties.items() if k not in _RESERVED_NODE_KEYS}
        with self._driver.session(database=self._database) as session:
            existing = session.run(
                "MATCH (n:KGNode {id: $id}) WHERE n.type IS NOT NULL "
                "RETURN n.type AS type, n.source_refs AS refs LIMIT 1",
                id=node.id,
            ).single()

            if existing is not None:
                if existing["type"] != node.type.value:
                    raise ValueError(
                        f"node id {node.id!r} already exists with type "
                        f"{existing['type']!r}; refusing to overwrite "
                        f"with type {node.type.value!r}"
                    )
                merged_refs = _ordered_union(existing["refs"] or [], node.source_refs)
            else:
                merged_refs = list(node.source_refs)

            session.run(
                "MERGE (n:KGNode {id: $id}) "
                "SET n.type = $type "
                "SET n += $props "
                "SET n.source_refs = $refs",
                id=node.id,
                type=node.type.value,
                props=safe_props,
                refs=merged_refs,
            )

    def upsert_edge(self, edge: KGEdge) -> None:
        """Insert or update an edge, applying the merge semantics from the Protocol."""
        self._require_connected()
        safe_props = {k: v for k, v in edge.properties.items() if k not in _RESERVED_EDGE_KEYS}
        with self._driver.session(database=self._database) as session:
            existing = session.run(
                "MATCH ()-[r {id: $id}]->() "
                "RETURN type(r) AS rel_type, r.source_refs AS refs LIMIT 1",
                id=edge.id,
            ).single()

            if existing is not None:
                if existing["rel_type"] != edge.type.value:
                    raise ValueError(
                        f"edge id {edge.id!r} already exists with type "
                        f"{existing['rel_type']!r}; refusing to overwrite "
                        f"with type {edge.type.value!r}"
                    )
                merged_refs = _ordered_union(existing["refs"] or [], edge.source_refs)
            else:
                merged_refs = list(edge.source_refs)

            session.run(
                "MERGE (s:KGNode {id: $source_id}) "
                "MERGE (t:KGNode {id: $target_id}) "
                "WITH s, t "
                "CALL apoc.merge.relationship(s, $rel_type, {id: $edge_id}, {}, t, {}) "
                "YIELD rel "
                "SET rel += $props "
                "SET rel.source_refs = $refs "
                "RETURN rel",
                source_id=edge.source_id,
                target_id=edge.target_id,
                rel_type=edge.type.value,
                edge_id=edge.id,
                props=safe_props,
                refs=merged_refs,
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> KGNode | None:
        self._require_connected()
        with self._driver.session(database=self._database) as session:
            record = session.run(
                "MATCH (n:KGNode {id: $id}) WHERE n.type IS NOT NULL RETURN n LIMIT 1",
                id=node_id,
            ).single()
            if record is None:
                return None
            return _record_to_node(record["n"])

    def neighbors(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        direction: Direction = "out",
    ) -> Sequence[KGNode]:
        self._require_connected()
        # Direction is a typed Literal, not user input — safe to interpolate.
        arrow_by_direction = {
            "out": "-[r]->",
            "in": "<-[r]-",
            "both": "-[r]-",
        }
        arrow = arrow_by_direction[direction]

        where_clauses = ["m.type IS NOT NULL"]
        params: dict[str, Any] = {"id": node_id}
        if edge_types is not None:
            where_clauses.append("type(r) IN $edge_types")
            params["edge_types"] = [et.value for et in edge_types]
        where = " AND ".join(where_clauses)

        cypher = (
            f"MATCH (n:KGNode {{id: $id}}){arrow}(m:KGNode) "
            f"WHERE {where} "
            "RETURN DISTINCT m "
            "ORDER BY m.id"
        )

        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, **params)
            nodes: list[KGNode] = []
            for record in result:
                node = _record_to_node(record["m"])
                if node is not None:
                    nodes.append(node)
            return tuple(nodes)

    def subgraph(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> Subgraph:
        self._require_connected()
        seeds = list(seed_ids)
        rel_filter = _build_relationship_filter(edge_types)

        cypher = (
            "MATCH (n:KGNode) "
            "WHERE n.id IN $seeds AND n.type IS NOT NULL "
            "WITH collect(n) AS starts "
            "WHERE size(starts) > 0 "
            "CALL apoc.path.subgraphAll(starts, { "
            "    maxLevel: $max_hops, "
            "    relationshipFilter: $rel_filter, "
            "    bfs: true "
            "}) YIELD nodes, relationships "
            "RETURN nodes, relationships"
        )

        with self._driver.session(database=self._database) as session:
            record = session.run(
                cypher,
                seeds=seeds,
                max_hops=max_hops,
                rel_filter=rel_filter,
            ).single()

            if record is None:
                return Subgraph()

            collected_nodes: list[KGNode] = []
            for raw in record["nodes"]:
                node = _record_to_node(raw)
                if node is not None:
                    collected_nodes.append(node)

            valid_ids = {n.id for n in collected_nodes}
            wanted = frozenset(edge_types) if edge_types is not None else None

            collected_edges: list[KGEdge] = []
            for raw in record["relationships"]:
                edge = _record_to_edge(raw)
                if edge is None:
                    continue
                if edge.source_id not in valid_ids or edge.target_id not in valid_ids:
                    continue
                if wanted is not None and edge.type not in wanted:
                    continue
                collected_edges.append(edge)

            return Subgraph(
                nodes=tuple(sorted(collected_nodes, key=lambda n: n.id)),
                edges=tuple(sorted(collected_edges, key=lambda e: e.id)),
            )

    def cascading_risk(
        self,
        start_id: str,
        *,
        max_hops: int = 3,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> Sequence[RiskPath]:
        self._require_connected()
        rel_filter = _build_relationship_filter(edge_types)

        cypher = (
            "MATCH (start:KGNode {id: $start_id}) "
            "WHERE start.type IS NOT NULL "
            "CALL apoc.path.expandConfig(start, { "
            "    minLevel: 1, "
            "    maxLevel: $max_hops, "
            "    relationshipFilter: $rel_filter, "
            "    bfs: true, "
            "    uniqueness: 'NODE_GLOBAL' "
            "}) YIELD path "
            "WITH path, last(nodes(path)) AS target "
            "WHERE target.type IS NOT NULL "
            "RETURN "
            "    target.id AS target_id, "
            "    length(path) AS hops, "
            "    [r IN relationships(path) | { "
            "        id: r.id, "
            "        type: type(r), "
            "        source_id: startNode(r).id, "
            "        target_id: endNode(r).id, "
            "        properties: properties(r), "
            "        source_refs: r.source_refs "
            "    }] AS edges "
            "ORDER BY hops, target_id"
        )

        with self._driver.session(database=self._database) as session:
            result = session.run(
                cypher,
                start_id=start_id,
                max_hops=max_hops,
                rel_filter=rel_filter,
            )
            paths: list[RiskPath] = []
            for record in result:
                edges = tuple(_edge_from_dict(raw) for raw in record["edges"])
                paths.append(
                    RiskPath(
                        start_id=start_id,
                        target_id=record["target_id"],
                        path=edges,
                        hops=int(record["hops"]),
                    )
                )
            return paths

    def shortest_path(self, source_id: str, target_id: str) -> Sequence[KGNode] | None:
        self._require_connected()
        cypher = (
            "MATCH (s:KGNode {id: $source_id}) "
            "WHERE s.type IS NOT NULL "
            "MATCH (t:KGNode {id: $target_id}) "
            "WHERE t.type IS NOT NULL "
            f"MATCH path = shortestPath((s)-[*..{_SHORTEST_PATH_MAX_EDGES}]->(t)) "
            "RETURN [n IN nodes(path) | properties(n)] AS node_props "
            "LIMIT 1"
        )
        with self._driver.session(database=self._database) as session:
            record = session.run(
                cypher,
                source_id=source_id,
                target_id=target_id,
            ).single()
            if record is None or not record["node_props"]:
                return None
            nodes: list[KGNode] = []
            for raw in record["node_props"]:
                node = _properties_to_node(raw)
                if node is None:
                    return None
                nodes.append(node)
            return tuple(nodes)

    def clear(self) -> None:
        self._require_connected()
        with self._driver.session(database=self._database) as session:
            session.run("MATCH (n) DETACH DELETE n")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if self._driver is None:
            raise RuntimeError("Neo4jBackend is not connected. Call connect() first.")

    def _verify_apoc_available(self) -> None:
        with self._driver.session(database=self._database) as session:
            try:
                record = session.run(
                    "CALL apoc.help('apoc') YIELD name RETURN count(name) AS apoc_count"
                ).single()
            except self._exceptions.ClientError as exc:
                if "no procedure" in str(exc).lower():
                    self._driver.close()
                    self._driver = None
                    raise RuntimeError(
                        "Neo4j backend requires the APOC plugin. "
                        "Install it on your Neo4j instance, or use the "
                        "NetworkX backend for local/test work."
                    ) from exc
                raise
            count = int(record["apoc_count"]) if record is not None else 0
            if count == 0:
                self._driver.close()
                self._driver = None
                raise RuntimeError(
                    "Neo4j backend requires the APOC plugin. "
                    "Install it on your Neo4j instance, or use the "
                    "NetworkX backend for local/test work."
                )

    def _ensure_constraints(self) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(
                "CREATE CONSTRAINT kg_node_id IF NOT EXISTS FOR (n:KGNode) REQUIRE n.id IS UNIQUE"
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _ordered_union(existing: Iterable[str], incoming: Iterable[str]) -> list[str]:
    """Deduplicating union that preserves first-seen ordering."""
    return list(dict.fromkeys([*existing, *incoming]))


def _build_relationship_filter(edge_types: Iterable[EdgeType] | None) -> str:
    """Render APOC's ``relationshipFilter`` argument from a Python iterable.

    An empty string means "all types, either direction" — exactly what
    :class:`NetworkXBackend`'s bidirectional BFS does when no filter is
    supplied. A non-empty filter ``"FOO|BAR"`` matches FOO or BAR in
    either direction (no directional prefix), matching the bidirectional
    contract.
    """
    if edge_types is None:
        return ""
    return "|".join(et.value for et in edge_types)


def _record_to_node(record_node: Any) -> KGNode | None:
    """Build a :class:`KGNode` from a neo4j Node record. Returns None if dangling."""
    if record_node is None:
        return None
    props = dict(record_node)
    node_id = props.pop("id", None)
    type_str = props.pop("type", None)
    if node_id is None or type_str is None:
        return None
    refs = props.pop("source_refs", None) or []
    return KGNode(
        id=node_id,
        type=NodeType(type_str),
        properties=props,
        source_refs=tuple(refs),
    )


def _record_to_edge(record_rel: Any) -> KGEdge | None:
    """Build a :class:`KGEdge` from a neo4j Relationship record."""
    if record_rel is None:
        return None
    props = dict(record_rel)
    edge_id = props.pop("id", None)
    if edge_id is None:
        return None
    refs = props.pop("source_refs", None) or []
    rel_type_value = record_rel.type
    try:
        edge_type = EdgeType(rel_type_value)
    except ValueError:
        return None
    start = record_rel.start_node
    end = record_rel.end_node
    if start is None or end is None:
        return None
    source_id = start.get("id")
    target_id = end.get("id")
    if source_id is None or target_id is None:
        return None
    return KGEdge(
        id=edge_id,
        source_id=source_id,
        target_id=target_id,
        type=edge_type,
        properties=props,
        source_refs=tuple(refs),
    )


def _edge_from_dict(raw: dict[str, Any]) -> KGEdge:
    """Build a :class:`KGEdge` from the dict shape returned by cascading_risk Cypher."""
    props = dict(raw.get("properties") or {})
    # The Cypher projection rolls everything from properties(r) into the
    # "properties" map, which still contains the schema-reserved keys.
    props.pop("id", None)
    props.pop("source_refs", None)
    return KGEdge(
        id=raw["id"],
        source_id=raw["source_id"],
        target_id=raw["target_id"],
        type=EdgeType(raw["type"]),
        properties=props,
        source_refs=tuple(raw.get("source_refs") or []),
    )


def _properties_to_node(props: dict[str, Any]) -> KGNode | None:
    """Build a :class:`KGNode` from a properties(n) map. Returns None if dangling."""
    if not props:
        return None
    node_id = props.get("id")
    type_str = props.get("type")
    if node_id is None or type_str is None:
        return None
    refs = props.get("source_refs") or []
    user_props = {k: v for k, v in props.items() if k not in _RESERVED_NODE_KEYS}
    return KGNode(
        id=node_id,
        type=NodeType(type_str),
        properties=user_props,
        source_refs=tuple(refs),
    )


__all__ = ["Neo4jBackend"]
