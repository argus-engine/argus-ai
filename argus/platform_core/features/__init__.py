# SPDX-License-Identifier: Apache-2.0
"""Cross-modal feature encoders and fusion layers.

`features` consumes `RawRecord` instances from `ingestion` and produces feature
tensors suitable for the predictive heads in `models`. The fusion strategy
(early concatenation, gated attention, late ensembling) is chosen by config.

**Phase 1 surface:** empty. The module exists to fix the import path and to
hold per-modality encoder interfaces when they land in Phase 2.

**Lands in later phases:**

- `TextEncoder` wrapping sentence-transformers (Phase 2)
- `TabularEncoder` for structured records with categorical / numeric mixing (Phase 2)
- `TimeSeriesEncoder` (Phase 2)
- `FusionLayer` strategies (Phase 3)
"""
