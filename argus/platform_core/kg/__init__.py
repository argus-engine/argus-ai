# SPDX-License-Identifier: Apache-2.0
"""Knowledge graph: records → triples → queryable subgraphs.

The KG layer constructs a typed graph (entities such as :class:`Supplier`,
:class:`Order`, :class:`EventSignal`; relations such as ``HAS_SUPPLIER``,
``AFFECTS``, ``SHIPS_TO``) from normalized records and exposes a
:class:`KGBackend` Protocol so the storage engine can be swapped (Neo4j
in production, NetworkX for local dev and tests).

**Phase 2 task #1 surface — schema, contracts, and builder skeleton:**

- :class:`NodeType` and :class:`EdgeType` — typed node and relationship labels.
- :class:`KGNode` and :class:`KGEdge` — frozen Pydantic schemas for graph entities.
- :func:`make_node_id` and :func:`make_edge_id` — stable, human-readable identifiers.
- :class:`KGBackend` — the storage-engine Protocol.
- :class:`KGBackendConfig` — configuration shared across backend implementations.
- :class:`Subgraph` and :class:`RiskPath` — typed query-result wrappers.
- :class:`KGAdapter` and :class:`KGBuilder` — ingestion orchestration.
- :class:`IngestionReport` — typed summary of one builder invocation.

**Lands in later Phase-2 tasks:**

- ``NetworkXBackend`` (Task #2) and ``Neo4jBackend`` (Task #3) implementations.
- The supply-chain :class:`KGAdapter` and end-to-end ingestion test (Task #4).
- ``cascading_risk`` and ``subgraph`` query implementations on both backends.
- ``docs/kg.md``, coverage gate flip, and the ``v0.2.0`` tag (Task #5).
"""

from argus.platform_core.kg.base import (
    Direction,
    KGBackend,
    KGBackendConfig,
    RiskPath,
    Subgraph,
)
from argus.platform_core.kg.builder import (
    IngestionReport,
    KGAdapter,
    KGBuilder,
)
from argus.platform_core.kg.schema import (
    EdgeType,
    KGEdge,
    KGNode,
    NodeType,
    make_edge_id,
    make_node_id,
)

__all__ = [
    "Direction",
    "EdgeType",
    "IngestionReport",
    "KGAdapter",
    "KGBackend",
    "KGBackendConfig",
    "KGBuilder",
    "KGEdge",
    "KGNode",
    "NodeType",
    "RiskPath",
    "Subgraph",
    "make_edge_id",
    "make_node_id",
]
