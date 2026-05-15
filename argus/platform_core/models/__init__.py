# SPDX-License-Identifier: Apache-2.0
"""Predictive heads and uncertainty-aware output schemas.

Every model output is an `UncertainPrediction` — point estimate plus a
calibrated confidence band — never a bare scalar. Domain packs may register
domain-tuned heads in `argus.domain_packs.<pack>.models`; the shared
output contract lives here.

**Phase 1 surface:** empty. The predictive-head abstractions land in Phase 3
together with the `UncertainPrediction` schema (decision F: deferred from
Phase 1 to land alongside the first head that needs it).

**Lands in Phase 3:**

- Baseline tabular models — LightGBM, XGBoost wrappers
- Evidential regression / classification heads
- `UncertainPrediction` Pydantic schema
- Cross-modal fusion strategies hosted in `features/`
"""
