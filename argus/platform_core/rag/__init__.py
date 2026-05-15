# SPDX-License-Identifier: Apache-2.0
"""Retrieval-augmented generation with a grounding rubric.

The RAG layer turns a query into `GroundedEvidence` — retrieved passages plus a
faithfulness score from the grounding rubric. Outputs that fail the rubric are
flagged before they reach the API or the human reviewer, never silently merged
into the prediction.

The `LLMProvider` interface gates every model call so the OpenAI implementation
can be swapped for a local model (vLLM, llama.cpp, Bedrock) without touching
caller code.

**Phase 1 surface:** empty.

**Lands in later phases:**

- `LLMProvider` Protocol + `OpenAIProvider` implementation (Phase 3)
- `Retriever` over the KG and a vector store (Phase 3)
- Grounding rubric + fabrication check (Phase 3)
"""
