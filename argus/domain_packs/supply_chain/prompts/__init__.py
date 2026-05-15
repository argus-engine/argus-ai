# SPDX-License-Identifier: Apache-2.0
"""Supply-chain prompt assets.

Prompts live as ``.j2`` / ``.txt`` files alongside this package and are loaded
through `argus.platform_core.rag` (Phase 3). Keeping prompts as data, not as
inline f-strings, makes them reviewable, diff-able, and swappable per
deployment.

**Phase 1 surface:** empty. Prompt assets land in Phase 3 with the RAG layer.
"""
