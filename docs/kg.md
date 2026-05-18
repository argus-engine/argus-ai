<!-- SPDX-License-Identifier: Apache-2.0 -->
# Knowledge graph

The knowledge-graph layer turns normalised domain records into a typed,
queryable subgraph. It is one of Argus's four extension points
(`Connector`, `KGBackend`, `LLMProvider`, `ReviewSink`); two backends
ship in-tree, and a new one is a config change, not a code change.

This document is the contract. It covers what the layer stores, how the
storage engine is selected, how ingestion stays idempotent across
repeated runs, what queries the rest of the platform calls, and what
Phase 3+ does with this surface.

## What the layer does

```
RawRecord       SupplyChainKGAdapter      KGBuilder.ingest()    KGBackend
   stream  ───>   (Pydantic entity →  ───>    (loops the    ───>   NetworkX
                  KGNode + KGEdge)             stream,             or Neo4j
                                               upserts             behind the
                                               nodes-first         same Protocol)
                                               then edges)
```

Three contracts make this composition safe:

1. **The Protocol seam.** Caller code depends on
   `argus.platform_core.kg.base.KGBackend` (a `runtime_checkable`
   `typing.Protocol`), never on a concrete backend. Test stubs satisfy
   it by duck typing; both shipped backends satisfy it without
   inheritance.
2. **Idempotency.** `upsert_node` and `upsert_edge` are safe to call
   repeatedly with the same input — the merge semantics are defined on
   the Protocol and identical on both backends.
3. **Order tolerance.** Edges referencing yet-unseen nodes are
   tolerated; real data streams arrive out of order across entities (a
   shipment may land before the order it fulfils).

## Schema

The schema is **domain-aware** (node and edge names read like
supply-chain vocabulary) but **engine-agnostic** (both backends store
the same `KGNode` / `KGEdge` Pydantic instances).

### Node types (`NodeType`)

Seven kinds — physical actors, the goods that move between them, the
geography they operate in, and the external signals that perturb them:

| Type | Purpose | Sourced from |
|---|---|---|
| `SUPPLIER` | A vendor / counterparty. Spine of the supply chain. | `Supplier.supplier_id` |
| `CUSTOMER` | An order's purchaser. | `Order.customer_id` (synthesised) |
| `PRODUCT` | A SKU that flows through orders. | `Order.product_id` (synthesised) |
| `ORDER` | One customer's line item for one product. | `Order.order_id` |
| `SHIPMENT` | A physical movement fulfilling an order. | `Shipment.shipment_id` |
| `REGION` | A macro geography (EMEA/NA/APAC/LATAM/AFRICA/OTHER). | `Region` enum value |
| `EVENT_SIGNAL` | External disruption signal (GDELT, EDGAR, news). | `EventSignal.event_id` |

`PRODUCT`, `CUSTOMER`, and `REGION` are first-class nodes because the
cascading-risk queries need to traverse to them as queryable entities,
not as opaque properties on parents.

### Edge types (`EdgeType`)

| Type | Direction | Sourced from |
|---|---|---|
| `HAS_SUPPLIER` | `Order → Supplier` | `Order.supplier_id` |
| `PLACED_BY` | `Order → Customer` | `Order.customer_id` |
| `OF_PRODUCT` | `Order → Product` | `Order.product_id` |
| `SHIPS_TO` | `Order → Region` (destination) | `Order.destination_region` |
| `FULFILS_ORDER` | `Shipment → Order` | `Shipment.order_id` |
| `SUPPLIED_BY` | `Shipment → Supplier` | `Shipment.supplier_id` |
| `LOCATED_IN` | `Supplier → Region` | `Supplier.region` |
| `DEPENDS_ON` | `Product → Supplier` | (reserved for BoM ingestion, Phase 3+) |
| `MENTIONS` | `EventSignal → any node` | `EventSignal.entities_mentioned`, resolved |
| `AFFECTS` | `EventSignal → any node` | (reserved for cascading-risk seeds, Phase 3+) |

Edge orientation encodes **foreign-key direction**, not impact-
propagation direction. A disruption at a supplier reaches its orders by
walking *incoming* `HAS_SUPPLIER` edges. Both backends' BFS therefore
walks bidirectionally — see [Queries](#queries) below.

### Stable identifiers

All node and edge ids come from `make_node_id` / `make_edge_id` —
never hand-constructed.

```
make_node_id(NodeType.SUPPLIER, "SUP-001")   → "supplier:SUP-001"
make_edge_id("order:O1",
             EdgeType.HAS_SUPPLIER,
             "supplier:SUP-001")              → "order:O1-HAS_SUPPLIER->supplier:SUP-001"
```

The format reads naturally in logs and the Neo4j browser. Re-running
ingestion on the same source key produces the same id, which is what
makes the upsert pipeline idempotent.

## Backends

Two implementations of `KGBackend` ship in-tree:

| Backend | Where it lives | When to use |
|---|---|---|
| `NetworkXBackend` | `argus.platform_core.kg.networkx_backend` | Unit tests, offline development, any deployment where a real graph database is overkill. In-process, `networkx.MultiDiGraph` under the hood. |
| `Neo4jBackend` | `argus.platform_core.kg.neo4j_backend` | Production. Talks to a Neo4j 5.x instance via the official driver; APOC required. |

### Selecting a backend

```python
from argus.platform_core.kg import KGBackendConfig, make_backend

# In-process NetworkX — `neo4j_*` fields ignored.
backend = make_backend("networkx", KGBackendConfig(name="local"))

# Neo4j over Bolt — `neo4j_*` fields are required.
backend = make_backend(
    "neo4j",
    KGBackendConfig(
        name="prod",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password=SecretStr("…"),
        neo4j_database="neo4j",
    ),
)

backend.connect()
try:
    # ... use the backend ...
finally:
    backend.disconnect()
```

`make_backend` lazy-imports the Neo4j driver so the platform stays
importable on a base install. Install the heavier dependencies with
`pip install argus-risk[kg]` to enable the Neo4j backend; until then,
construction raises `ImportError` with a clear message.

### The APOC requirement

`Neo4jBackend.connect()` verifies that APOC is installed by calling
`apoc.help('apoc')` and counting the results. If APOC is missing the
call raises:

```
RuntimeError: Neo4j backend requires the APOC plugin.
Install it on your Neo4j instance, or use the NetworkX backend
for local/test work.
```

Why APOC: cascading-risk and subgraph queries use
`apoc.path.expandConfig` and `apoc.path.subgraphAll` for bidirectional
BFS with a hop limit; upsert uses `apoc.merge.relationship` to create
typed relationships from a dynamic edge-type string. None has a clean
non-APOC equivalent in Cypher.

For local development, the docker-compose `neo4j` service ships APOC
pre-installed; integration tests use a testcontainers-spawned Neo4j
with the same APOC environment.

## Ingestion

`KGBuilder` is a thin orchestrator: iterate the entity stream, ask the
adapter for `(nodes, edges)` per entity, forward to the backend's
upsert methods. Per-entity ordering: **nodes first, then edges**, so
endpoints-first backends see them that way.

### Merge semantics (binding on every backend)

When an `upsert_node` call hits an existing id:

- **`type` MUST match.** Re-upserting an id with a different `NodeType`
  is a bug — raises `ValueError`. The backend will not silently
  overwrite, say, a supplier with a customer at the same key.
- **`properties` merge per key.** Incoming values override existing
  values for the same key; existing keys absent from the incoming
  payload are preserved.
- **`source_refs` union with deduplication, first-seen order.** The
  provenance trail accumulates across repeated ingest of the same
  logical entity.

`upsert_edge` mirrors these rules exactly, keyed on `edge.id`.

### Worked example: idempotent re-ingest

```python
from argus.platform_core.kg import KGNode, NodeType, make_node_id

backend.upsert_node(
    KGNode(
        id=make_node_id(NodeType.SUPPLIER, "SUP-001"),
        type=NodeType.SUPPLIER,
        properties={"name": "Acme", "country": "GB"},
        source_refs=("dataco:row-7",),
    )
)
backend.upsert_node(
    KGNode(
        id=make_node_id(NodeType.SUPPLIER, "SUP-001"),  # same id
        type=NodeType.SUPPLIER,                          # same type — required
        properties={"country": "US", "industry_sic": "3711"},
        source_refs=("edgar:CIK-12345",),
    )
)

assert backend.get_node("supplier:SUP-001") == KGNode(
    id="supplier:SUP-001",
    type=NodeType.SUPPLIER,
    properties={
        "name": "Acme",         # preserved from the first upsert
        "country": "US",        # overridden by the second
        "industry_sic": "3711", # added by the second
    },
    source_refs=("dataco:row-7", "edgar:CIK-12345"),  # union, first-seen order
)
```

Same source, run twice → same final state. Different sources for the
same entity → merged record with both provenance refs.

### Ingestion order for the supply-chain adapter

`SupplyChainKGAdapter` is stateful within a single build:
`EventSignal.entities_mentioned` is resolved against the suppliers,
products, and customers seen so far. **The caller must feed entities in
the order `Suppliers → Orders → Shipments → EventSignals`.** Out-of-
order ingest is not an error — it produces silent unresolved mentions,
visible on `IngestionReport.adapter_counters["unresolved_mentions"]`.

The fixture builder in `tests/domain_packs/supply_chain/kg/fixtures.py`
demonstrates the correct order; the end-to-end test pins it.

## Queries

Every query goes through the `KGBackend` Protocol. The Python surface
is identical across backends; the underlying mechanism differs.

### Neighbours

```python
neighbors = backend.neighbors(
    "supplier:SUP-001",
    edge_types=[EdgeType.HAS_SUPPLIER],
    direction="in",        # incoming HAS_SUPPLIER → the orders this supplier serves
)
```

| NetworkX | Neo4j (Cypher) |
|---|---|
| `MultiDiGraph.in_edges(node_id, keys=True)` filtered to typed edges | `MATCH (n:KGNode {id: $id})<-[r]-(m:KGNode) WHERE type(r) IN $types RETURN m` |

### Cascading risk

Returns the ordered list of downstream-impact paths from a seed, depth-
bounded:

```python
paths = backend.cascading_risk(
    "supplier:SUP-001",
    max_hops=3,
)
for risk_path in paths:
    print(risk_path.target_id, risk_path.hops)
```

`RiskPath` carries the seed, the target, the ordered edge sequence, and
the hop count. Results are sorted by `(hops, target_id)` for
determinism; both backends produce byte-identical sequences for the
same input graph.

| NetworkX | Neo4j (Cypher with APOC) |
|---|---|
| BFS over `MultiDiGraph` with both `out_edges` and `in_edges` expanded at every hop; visited-set deduplication; results sorted by `(hops, target_id)` | `apoc.path.expandConfig(start, {maxLevel: $h, bfs: true, uniqueness: 'NODE_GLOBAL', relationshipFilter: $rel_filter})` with `relationshipFilter` left empty (or `"TYPE1|TYPE2"`, no directional prefix) for bidirectional traversal |

### Subgraph extraction

The primitive Phase 4 RAG retrieval uses: given the entities a query
mentions, return the typed neighbourhood the LLM should be grounded
against.

```python
sg = backend.subgraph(
    seed_ids=["supplier:SUP-001", "region:EMEA"],
    max_hops=2,
    edge_types=None,        # all types
)
print(len(sg.nodes), len(sg.edges))
```

`Subgraph` is the **induced** subgraph: every edge between any two
collected nodes is returned, not just the spanning-tree edges traversed
during BFS.

| NetworkX | Neo4j (Cypher with APOC) |
|---|---|
| Bidirectional BFS collects reachable node ids; a second pass over `MultiDiGraph.edges` retains edges whose both endpoints are in the collected set and pass the edge-type filter | `apoc.path.subgraphAll(starts, {maxLevel: $h, bfs: true, relationshipFilter: $rel_filter})` then a Python-side filter to retain only edges whose both endpoints are in the returned node set |

### Shortest path

```python
node_chain = backend.shortest_path(
    "supplier:SUP-001",
    "customer:CUST-99",
)
```

Returns `None` if no path exists, or if any intermediate node is a
dangling endpoint (referenced by an edge but never upserted). Path
length is hard-capped at 20 edges — longer paths return `None` rather
than risking a runaway traversal.

| NetworkX | Neo4j (Cypher) |
|---|---|
| `networkx.shortest_path(graph, source, target)` then materialise to `KGNode`s | `MATCH path = shortestPath((s)-[*..20]->(t)) RETURN [n IN nodes(path) \| properties(n)]` |

## Reports

`KGBuilder.ingest` returns an `IngestionReport`:

```python
report = KGBuilder(backend, adapter).ingest(entity_stream)
print(report.nodes_seen, report.edges_seen, report.duration_ms)
print(report.adapter_counters)   # e.g. {"unresolved_mentions": 3}
```

`adapter_counters` is the seam pack-specific adapters use to surface
diagnostic counts (like the supply-chain adapter's
`unresolved_mentions`) without coupling the platform-core
`IngestionReport` to pack-specific concepts. Adapters that have nothing
to report return an empty mapping.

## What Phase 3+ does with this layer

| Phase | How it uses the KG |
|---|---|
| **3 — predictive head** | Cascading-risk paths from a candidate event feed the model's KG-context features. The predictive head treats `RiskPath.hops` and the typed edge sequence as inputs alongside the tabular features. |
| **4 — RAG + grounding** | `subgraph()` is the primitive the retriever calls when the user asks a question about a named entity. The induced subgraph (nodes + edges) is the grounding evidence the LLM must agree with; the rubric checks that every claim in the answer is anchored in this returned subgraph. |
| **5 — HITL** | Reviewer disagreements reference KG entity ids directly. The active-learning loop can re-weight `MENTIONS` edges based on which mentions human reviewers confirmed or rejected. |

The Protocol guarantees these phases can swap NetworkX for Neo4j (or
either for a future ArangoDB / Memgraph backend) without touching their
own code.

## See also

- [`architecture.md`](architecture.md) — the layering contract and the
  KG layer's position in it
- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — current phase status
- `argus/platform_core/kg/base.py` — the `KGBackend` Protocol with full
  per-method docstrings
- `tests/domain_packs/supply_chain/kg/fixtures.py` — the hand-traced
  topology + expected query results used by the flagship tests
