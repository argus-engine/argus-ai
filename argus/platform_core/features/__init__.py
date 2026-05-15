# SPDX-License-Identifier: Apache-2.0
"""Cross-modal feature encoders and fusion layers.

`features` consumes `RawRecord` instances from `ingestion` and produces feature
tensors suitable for the predictive heads in `models`. The fusion strategy
(early concatenation, gated attention, late ensembling) is chosen by config.

**Phase 1 surface:** empty. The module exists to fix the import path and to
hold per-modality encoder interfaces when they land in Phase 3.

**Lands in later phases:**

- `TabularEncoder` for structured records with categorical / numeric mixing (Phase 3)
- `TextEncoder` wrapping sentence-transformers (Phase 3)
- `TimeSeriesEncoder` (Phase 3)
- `FusionLayer` strategies (Phase 3)
"""
