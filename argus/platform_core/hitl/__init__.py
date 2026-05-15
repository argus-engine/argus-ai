# SPDX-License-Identifier: Apache-2.0
"""Human-in-the-loop: review queue and active-learning feedback.

HITL is a design pillar, not a feature flag. Predictions that fall below a
configured confidence threshold, or that are flagged by the grounding rubric,
are routed to a review queue. Reviewer judgments — including structured
disagreements with the model's reasoning — are captured and fed back as
training signal.

**Phase 1 surface:** empty.

**Lands in later phases:**

- `ReviewSink` Protocol so the reviewer transport (Streamlit / Slack / Linear)
  is pluggable (Phase 4)
- Disagreement schema and active-learning feedback loop (Phase 4)
- Reviewer dashboard wiring (Phase 4)
"""
