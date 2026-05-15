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

**Lands in Phase 4:**

- `LLMProvider` Protocol + `OpenAIProvider` implementation
- `Retriever` over the KG and a vector store
- Grounding rubric + fabrication check
- Pack-specific prompt assets loaded from each pack's ``prompts/`` directory
"""
