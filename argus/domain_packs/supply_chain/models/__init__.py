# SPDX-License-Identifier: Apache-2.0
"""Supply-chain-tuned predictive heads.

Pack-level models inherit from `argus.platform_core.models` abstractions and
specialize them with supply-chain-aware features (e.g., supplier embeddings
keyed by KG node, time-decayed event-signal aggregations).

**Phase 1 surface:** empty. First model — a LightGBM disruption baseline — lands
in Phase 3, alongside the evidential heads.
"""
