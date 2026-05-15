# SPDX-License-Identifier: Apache-2.0
"""Knowledge graph: records → triples → queryable subgraphs.

The KG layer constructs a typed graph (entities such as Supplier, Order, Event;
relations such as `supplies`, `disrupts`, `routes_through`) from normalized
records and exposes a `KGBackend` interface so the storage engine can be
swapped (Neo4j in production, NetworkX for local dev and tests).

**Phase 1 surface:** empty. Module exists to fix the import path.

**Lands in later phases:**

- `KGBackend` Protocol with `Neo4jBackend` and `NetworkXBackend` implementations (Phase 2)
- Schema definitions for entities and relations (Phase 2)
- Subgraph extraction utilities used by `rag` and `models` (Phase 2)
"""
