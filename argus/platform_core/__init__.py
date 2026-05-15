# SPDX-License-Identifier: Apache-2.0
"""Domain-agnostic core of the Argus platform.

`platform_core` is the substrate that every domain pack builds on. It owns the
ingestion, feature, knowledge-graph, modeling, retrieval, human-in-the-loop, and
API layers. None of its sub-modules know what supply chains are — that
specialization lives in `argus.domain_packs`.

The layering contract is strictly downward (see `docs/architecture.md`):
`api` may compose all lower layers; `hitl` consumes from `models`; `models`
and `rag` consume from `features` and `kg`; `features` and `kg` consume from
`ingestion`. Cross-layer dependencies in the reverse direction are review
blockers.
"""
