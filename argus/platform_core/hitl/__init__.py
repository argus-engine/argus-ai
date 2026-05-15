# SPDX-License-Identifier: Apache-2.0
"""Human-in-the-loop: review queue and active-learning feedback.

HITL is a design pillar, not a feature flag. Predictions that fall below a
configured confidence threshold, or that are flagged by the grounding rubric,
are routed to a review queue. Reviewer judgments — including structured
disagreements with the model's reasoning — are captured and fed back as
training signal.

**Phase 1 surface:** empty.

**Lands in Phase 5:**

- `ReviewSink` Protocol so the reviewer transport (Streamlit / Slack / Linear)
  is pluggable
- Disagreement schema and active-learning feedback loop into Phase-3 models
- Streamlit reviewer dashboard wiring
- Evaluation harness (calibration, coverage, grounding fidelity, subgroup
  performance)
"""
