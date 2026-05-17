# SPDX-License-Identifier: Apache-2.0
"""Knowledge graph: records → triples → queryable subgraphs.

The KG layer constructs a typed graph (entities such as :class:`Supplier`,
:class:`Order`, :class:`EventSignal`; relations such as ``HAS_SUPPLIER``,
``AFFECTS``, ``SHIPS_TO``) from normalized records and exposes a
:class:`KGBackend` Protocol so the storage engine can be swapped (Neo4j
in production, NetworkX for local dev and tests).

**Phase 2 tasks #1 and #2 — schema, contracts, builder, NetworkX backend:**

- :class:`NodeType` and :class:`EdgeType` — typed node and relationship labels.
- :class:`KGNode` and :class:`KGEdge` — frozen Pydantic schemas for graph entities.
- :func:`make_node_id` and :func:`make_edge_id` — stable, human-readable identifiers.
- :class:`KGBackend` — the storage-engine Protocol.
- :class:`KGBackendConfig` — configuration shared across backend implementations.
- :class:`Subgraph` and :class:`RiskPath` — typed query-result wrappers.
- :class:`KGAdapter` and :class:`KGBuilder` — ingestion orchestration.
- :class:`IngestionReport` — typed summary of one builder invocation.
- :class:`NetworkXBackend` — in-process backend on :class:`networkx.MultiDiGraph`.
- :func:`make_backend` — factory mapping a backend name to an implementation.

**Lands in later Phase-2 tasks:**

- ``Neo4jBackend`` (Task #3) + ``@pytest.mark.integration`` tests via testcontainers.
- The supply-chain :class:`KGAdapter` and end-to-end ingestion test (Task #4).
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
from argus.platform_core.kg.factory import make_backend
from argus.platform_core.kg.networkx_backend import NetworkXBackend
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
    "NetworkXBackend",
    "NodeType",
    "RiskPath",
    "Subgraph",
    "make_backend",
    "make_edge_id",
    "make_node_id",
]
