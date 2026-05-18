<!-- SPDX-License-Identifier: Apache-2.0 -->
# Architecture

This document is the contract between the modules in Argus. The README is the pitch; this is the layering rulebook.

If you propose a change that affects what lives where, or how two layers talk, update this document in the same PR.

## Goals

Argus is shaped by four non-negotiable goals:

1. **Domain-agnostic core, pluggable verticals.** The core does not know what supply chains are. The supply-chain pack
   does not modify the core; it composes with it.
2. **Every external dependency is swappable.** LLM provider, KG backend, cloud target, ingestion source. We assume each
   will be replaced at least once over the platform's lifetime.
3. **Uncertainty and grounding are first-class outputs.** A prediction is not just `(y_hat, p)` — it carries a confidence
   band, attribution, and the evidence that supports it.
4. **HITL is in the platform.** Review, disagreement capture, and active-learning feedback are core modules, not a
   downstream add-on.

## Top-level structure

```
argus/                          # Python package
├── platform_core/              # domain-agnostic primitives
│   ├── ingestion/              # boundary: external data → normalized records
│   ├── features/               # boundary: records → feature tensors
│   ├── kg/                     # boundary: records → knowledge-graph triples / queries
│   ├── models/                 # boundary: features + KG context → predictions
│   ├── rag/                    # boundary: queries → grounded retrieved evidence
│   ├── hitl/                   # boundary: prediction + reviewer → labeled outcome
│   └── api/                    # boundary: HTTP → all of the above
└── domain_packs/
    └── <pack>/                 # composes platform_core for a specific vertical
        ├── data/               # pack-specific schemas + loaders
        ├── prompts/            # pack-specific prompt assets
        ├── models/             # pack-specific heads / fine-tunes
        └── evaluation/         # pack-specific benchmarks
```

## Layering contract

**Direction of dependence is strictly downward in the list below.** A higher layer may import from a lower one; the
reverse is a layering violation and a review-blocker.

```
api          ← composes all lower layers; HTTP shell only, no business logic
↓
hitl         ← consumes predictions, emits labeled feedback
↓
models       ← consumes features + KG context, emits predictions
rag          ← consumes KG queries, emits grounded evidence (peer of models)
↓
features     ← consumes records, emits tensors
kg           ← consumes records, emits triples (peer of features)
↓
ingestion    ← consumes external data, emits normalized records
```

`domain_packs` may depend on **any** layer of `platform_core` but never on another domain pack.

## Plugin boundaries

Argus has four extension points. Each is an abstract base class or `Protocol` under `argus.platform_core`:

| Extension point | Interface | What you'd swap |
|---|---|---|
| Ingestion source | `Connector` (`argus.platform_core.ingestion.base`) | A new file format, API, or stream |
| KG backend | `KGBackend` (`argus.platform_core.kg.base`, delivered in Phase 2 — `v0.2.0`) | Neo4j → NetworkX, ArangoDB, Memgraph |
| LLM | `LLMProvider` (lands in Phase 4) | OpenAI → local model, vLLM, Bedrock |
| Reviewer transport | `ReviewSink` (lands in Phase 5) | Streamlit UI → Slack interactive, Linear ticket |

Phase 1 shipped `Connector`. Phase 2 added `KGBackend` plus its NetworkX and Neo4j implementations, the supply-chain
`KGAdapter` that projects the four supply-chain entities onto typed nodes/edges, and the `KGAdapter.counters()` /
`IngestionReport.adapter_counters` seam for pack-specific diagnostic counts. `LLMProvider` and `ReviewSink` still
surface in later phases — stubbing them ahead of their implementations was discussed and explicitly deferred (see
decisions F and G in `memory/`-tracked Phase 1 decisions). See [`kg.md`](kg.md) for the as-built KG layer.

## Data flow: a single prediction's lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Caller (API or batch job)
    participant Ing as ingestion.Connector
    participant Feat as features
    participant KG as kg
    participant RAG as rag
    participant Model as models
    participant API
    participant HITL as hitl (optional)

    Caller->>Ing: pull(records since T)
    Ing-->>Caller: Iterator[RawRecord]
    Caller->>Feat: encode(records)
    Caller->>KG: upsert(records)
    Caller->>Model: predict(features, kg_context)
    Model->>RAG: retrieve_evidence(query) (optional)
    RAG-->>Model: GroundedEvidence
    Model-->>API: UncertainPrediction (Phase 3 schema; RAG evidence per Phase 4)
    API-->>Caller: JSON response (point + band + evidence)
    opt low confidence
        API->>HITL: enqueue_for_review(prediction)
        HITL-->>Model: labeled feedback (active learning)
    end
```

Phase 1 covered steps 1–2 (ingestion). Phase 2 added step 4 (KG upsert) plus the cascading-risk and subgraph queries
the later phases will read from. Steps 3, 5–9 land across Phases 3–5.

## Configuration

All configuration is YAML under `configs/`. Code consumes it through `pydantic-settings` (decision E) — never via
`os.environ` or `open("…").read()` directly.

```
configs/
├── default.yaml                # base config
├── local.yaml                  # local dev overrides (git-ignored if it contains secrets)
└── packs/
    └── supply_chain.yaml       # pack-specific config
```

Environment variables override YAML, in 12-factor style. The override schema is defined alongside the YAML schema in
`pydantic-settings` classes.

## Observability

(Phase 6.) Structured logging via `structlog` from day one. OpenTelemetry traces, Prometheus metrics, and a Grafana
dashboard land with the Terraform multi-cloud rollout. Every log line carries `request_id`, `model_version`, and `pack_name`.

## Security and data governance

- Secrets never live in code or `configs/`. The container reads them from env vars or a mounted secret file at startup.
- Datasets in `data/` are git-ignored; only ~100-row fixtures in `tests/fixtures/` are committed.
- PII handling rules live in [`responsible_ai.md`](responsible_ai.md).

## What this document is not

This is the **as-built** architecture, kept in lockstep with the code. Speculative architecture (ideas being evaluated)
lives in `docs/proposals/` once that directory exists. Don't pollute this document with options not yet adopted.
