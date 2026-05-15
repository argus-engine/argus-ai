<!-- SPDX-License-Identifier: Apache-2.0 -->
# Responsible AI

Argus targets high-stakes decisions. A platform that predicts supplier failures, credit defaults, or operational risk
can cause real harm if deployed without thinking carefully about *who it works for*, *who it works against*, and *what
it should not be used for*. This document sets that frame.

## Intended use

Argus is intended as a **decision-support tool for trained analysts** operating inside an organization with the
authority to act on the risks it surfaces. Concretely:

- A supply-chain operations team reviewing forecasted disruption risk across active suppliers.
- A risk officer triaging alerts about counterparty exposure.
- A research engineer evaluating multimodal risk-modeling methodology.

Every output Argus produces is accompanied by uncertainty, attribution, and retrieved evidence so the analyst can
verify the model's reasoning, not just its conclusion.

## Out-of-scope uses

Argus is **not** intended for, and we will not knowingly support:

- **Fully automated decisions affecting individuals** (credit, employment, insurance, immigration, healthcare access).
  Argus produces uncertain, evidence-linked predictions designed for human review; configuring it as a closed-loop
  decision system on individuals is a misuse.
- **Adversarial profiling** of individuals or organizations not party to the deploying organization's legitimate
  business relationships.
- **Real-time consumer-facing scoring** where the user being scored has no recourse or visibility.
- **Use in jurisdictions or contexts where the input data was not lawfully obtained or licensed.** Argus does not
  validate the legal status of upstream data on your behalf.

If your use case sits in a grey area, the design principle is: *would a reviewer with subpoena power be comfortable
with how this is being used?* If not, stop.

## Known limitations

We are deliberate about what Argus does *not* yet do well.

| Limitation | Practical impact | Mitigation |
|---|---|---|
| **Calibration drift** | Uncertainty estimates are calibrated on training data; real-world drift degrades them. | Phase 4 ships an evaluation harness that re-checks calibration on incoming feedback labels. |
| **Long-tail event coverage** | Models trained on historical data underestimate rare regimes (e.g. pandemic-scale shocks). | Surface KG-derived event signals separately so analysts see the qualitative shift even when the model's probability is low. |
| **Citation faithfulness** | RAG retrieval finds relevant evidence but does not guarantee the model's *claim* is supported by it. | Phase 3 ships a grounding rubric that checks claim ↔ evidence alignment and flags unsupported assertions. |
| **Language coverage** | Text encoders are strongest in English; performance degrades in low-resource languages. | Document the language coverage of each prompt/model asset; default to flagging low-confidence translations for review. |
| **Geographic and sector skew** | Public datasets (DataCo, GDELT, EDGAR) over-represent North American and Western European actors. | The supply-chain pack documents its training distribution; users should expect degraded performance outside it. |

## Bias considerations

Risk modeling is unusually exposed to feedback-loop bias: a model that under-predicts a region's reliability causes
fewer orders, which produces fewer data points, which deepens the under-prediction.

Argus's response is structural, not just statistical:

- **Counterfactual surfacing.** When uncertainty is high, the HITL surface (Phase 4) presents the closest counterfactual
  the model considered, so the reviewer sees what *would* have changed the prediction.
- **Disagreement capture.** Reviewer disagreements with the model are stored alongside predictions, not just used as
  retraining labels — so we can audit whether the model is systematically wrong about a sub-population.
- **Pack-level documentation.** Each domain pack ships a model card (`domain_packs/<pack>/evaluation/MODEL_CARD.md`)
  describing training data composition, known performance gaps, and fairness metrics where applicable.

## Data governance

- **PII.** Argus is designed around organizational data (suppliers, shipments, filings). When data describing
  individuals enters the system, it must be pseudonymized at the ingestion boundary. Connectors that touch PII expose a
  `pii_strategy` field on their config; the default is `reject`.
- **Provenance.** Every `RawRecord` produced by a connector carries a `source` field identifying where it came from.
  Downstream artifacts (features, KG triples, predictions) carry the provenance trail forward so we can answer "which
  source contributed to this prediction?"
- **Retention.** The platform itself does not retain data — it processes records into derived artifacts. The deploying
  organization is responsible for retention policies on raw sources. Defaults in `infra/` provision short retention
  windows (≤30 days) for cached raw data.
- **Source licensing.** The supply-chain pack uses DataCo (Kaggle, see Kaggle's terms of use), GDELT 2.0 (public, CC BY
  4.0 attribution required), and SEC EDGAR (public domain, with the SEC's published usage limits). The pack respects
  each source's attribution and rate-limit requirements.

## Evaluation expectations

The platform refuses to be evaluated only on point-prediction accuracy. The evaluation harness (lands in Phase 4)
reports, at minimum:

- Point-prediction accuracy with confidence intervals.
- **Calibration**: reliability diagrams and expected-calibration-error.
- **Coverage**: fraction of held-out events that fall within the model's stated confidence band.
- **Grounding fidelity**: fraction of RAG citations actually supporting the claim they were attached to (Phase 3+).
- **Subgroup performance** across the dimensions documented in each pack's model card.

A model that wins on accuracy but loses on calibration or coverage is not shipped.

## Auditability

Every prediction served via the API is recorded with: model version, config snapshot, input record IDs, retrieved
evidence IDs, and uncertainty. This trace lets a reviewer reconstruct *exactly* the inputs and reasoning behind a
historical decision. The retention window for this trace is configurable per deployment but defaults to 90 days.

## Reporting concerns

If you observe Argus behaving in a way that conflicts with this document, please open a GitHub issue tagged
`responsible-ai`. If the concern involves sensitive information, contact the maintainers privately first.
