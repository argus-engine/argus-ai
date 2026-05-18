<!-- SPDX-License-Identifier: Apache-2.0 -->
# Project context

**Living document. Update at the end of every phase as part of phase closeout.**
This is the fastest path for any AI assistant (or human collaborator) to come
up to speed on Argus. If you can't get full context from this in under a
minute, the file has bloated — trim it.

## TL;DR

**Argus** is an open-source, multi-cloud platform for **explainable, uncertainty-
aware risk prediction** in high-stakes domains. It has a domain-agnostic core
(`argus.platform_core`) and pluggable **domain packs** (`argus.domain_packs.*`).
First reference pack: supply-chain disruption forecasting (DataCo + GDELT + SEC EDGAR).

Three load-bearing claims:
1. **Uncertainty is a first-class output** — every prediction carries a calibrated band.
2. **Every prediction is grounded** — model output paired with retrieved evidence + grounding-rubric check.
3. **HITL is a design pillar** — review queue, structured disagreements, active-learning feedback are core modules.

Stack: Python 3.11+, Pydantic v2, FastAPI, PyTorch, sklearn/XGBoost/LightGBM, HF transformers, Neo4j (NetworkX fallback), OpenAI behind an interface, Streamlit, Terraform (GCP+AWS), Docker multi-arch, GitHub Actions, pytest.

## Author & contact

**Soheil Jafarifard Bidgoli** <soheiljafarifard@gmail.com>
Portfolio repo for senior ML/AI roles — headline target is the KTP Associate role at Aston University × Modular Data Ltd.

## Phase plan

| Phase | Scope | Status |
|---|---|---|
| **1. Scaffold + ingestion + docs + CI** | Repo skeleton, packaging, ingestion ABCs + connectors, supply-chain schemas + loaders, source downloaders, CI, Docker, docs | ✅ **complete** — `v0.1.0` |
| **2. Knowledge graph engine** | Neo4j construction from supply-chain entities, cascading-risk + subgraph queries, NetworkX fallback, `KGBackend` Protocol, supply-chain `KGAdapter`, integration tests on real Neo4j | ✅ **complete** — `v0.2.0` |
| **3. Predictive head with evidential uncertainty** | Baseline tabular models (LightGBM, XGBoost), evidential regression / classification heads, cross-modal fusion, `UncertainPrediction` schema | ⏭ **next** |
| **4. RAG + grounding rubric + fabrication check** | `LLMProvider` (OpenAI + local), retriever over KG + vector store, grounding rubric, fabrication check, pack-specific prompt assets | not started |
| **5. HITL dashboard + active learning loop** | Streamlit reviewer dashboard, `ReviewSink` Protocol, disagreement schema, active-learning feedback into Phase-3 models, evaluation harness (calibration / coverage / grounding fidelity) | not started |
| **6. Terraform multi-cloud deployment** | Terraform modules for GCP + AWS, multi-arch image push, K8s manifests, OpenTelemetry traces, Prometheus + Grafana | not started |

Each phase ends with a tagged release, refreshed `docs/architecture.md`, and runnable acceptance criteria.

**No Phase 7.** Polish items that are recruiter-visible (README, quickstart, badges, working demos, examples) live in Task #14 of Phase 1, not a separate phase — this is a portfolio project under a 14-day Phase-1 deadline and scope must stay disciplined.

## Where we are now

**Phase 1 + Phase 2 complete (tagged `v0.1.0` and `v0.2.0`).** Phase 3
(predictive head with evidential uncertainty) is next.

Phase-1 task ledger (all complete):

1. ✅ Packaging foundation (pyproject.toml, LICENSE, .gitignore, .python-version)
2. ✅ README with pitch + mermaid diagram + quickstart
3. ✅ `docs/architecture.md` + `docs/responsible_ai.md` + `CONTRIBUTING.md`
4. ✅ Full module skeleton with phase-boundary docstrings
5. ✅ Pre-commit + conventional commits + SPDX header check + Makefile
6. ✅ `Connector` ABC + Pydantic record schemas
7. ✅ Three concrete connectors: `StructuredCSVConnector`, `TextDocumentConnector`, `TimeSeriesConnector`
8. ✅ Supply-chain schemas (`Order`/`Supplier`/`Shipment`/`EventSignal`) + loaders + tests *(draft-PR red-line process)*
9. ✅ `scripts/download_data.py` + `scripts/build_fixtures.py` *(DataCo, bounded GDELT, EDGAR sample)*
10. ✅ GitHub Actions CI (lint / typecheck / test matrix / security / docker-build)
11. ✅ Multi-stage Dockerfile (cpu / gpu / streamlit) + `docker-compose.yml` with `--profile gpu`
12. ✅ Polish: README badges, terraform stubs, `argus --help` subcommand structure, clean-clone quickstart verification, `v0.1.0` tag

**State at the close of Phase 1:** **`v0.1.0` tag**, ≈33 commits on `main`, **233 tests passing in ≈4s**, zero live-API calls in CI, clean-clone install verified end-to-end (uvicorn → `/health` round-trip).

Phase-2 task ledger (all complete):

1. ✅ KG schema (`NodeType`, `EdgeType`, `KGNode`, `KGEdge`, stable-id helpers), `KGBackend` Protocol with merge semantics, `KGAdapter` Protocol, `KGBuilder` orchestrator, `IngestionReport`
2. ✅ `NetworkXBackend` (in-process), `make_backend` factory with lazy `[kg]`-extras import, contract tests
3. ✅ `Neo4jBackend` (production), APOC-availability check, message-scoped suppression of two `testcontainers` deprecation warnings, parametrised parity tests over both backends with `@pytest.mark.integration`
4. ✅ `SupplyChainKGAdapter` projecting all four supply-chain entities to typed nodes/edges with four-rule mention resolution, `unresolved_mentions` counter surfaced via new `KGAdapter.counters()` seam → `IngestionReport.adapter_counters`; deterministic flagship fixture; cascading-risk + subgraph + end-to-end tests parametrised over both backends
5. ✅ `docs/kg.md` reader-facing doc, coverage gate flipped from report-only to enforced at 83%, this update, `v0.2.0` tag

**State at the close of Phase 2:** **`v0.2.0` tag**, **396 tests passing + 1 skipped + 42 deselected (integration) in ≈5s** locally; **integration job green in CI on real Neo4j 5.20-community + APOC via testcontainers**; coverage gate enforced at 83% (current measured = 83.5%); no AI attribution anywhere in tree or history.

**In-flight design changes worth recording (vs the plan as posed at Phase-2 open):**

- The `KGAdapter` Protocol gained an optional `counters() -> Mapping[str, int]` method so pack-specific adapters can surface diagnostic counts (like the supply-chain adapter's `unresolved_mentions`) without coupling `platform_core` to a supply-chain concept. The new field on `IngestionReport` is `adapter_counters: dict[str, int]`.
- Backend test fixtures (`neo4j_container`, `backend`, etc.) were hoisted from `tests/platform_core/kg/conftest.py` to `tests/conftest.py` so the supply-chain flagship tests share one Neo4j container per pytest session with the parity tests. The original "layer-specific fixtures live alongside the layer" convention was relaxed because the KG infrastructure is now organically cross-cutting.
- The flagship cascade fixture topology produces 16 RiskPaths at `max_hops=2` from `supplier:SUP-A` (not 15 as the plan-readback approximated); the off-by-one is `region:NA` reached at hop 2 via `O4 -SHIPS_TO-> NA`. The five-node exclusion set is `{SUP-B, O5, P3, SH-O5, E2}` — E2 is structurally SUP-B-side via its incoming `MENTIONS` edges. The fixture's module docstring is the test contract; counts and exclusions are pinned there.
- Two `testcontainers` deprecation warnings (the `@wait_container_is_ready` decorator and the `wait_for_logs` string-predicate form) had to be suppressed via message-scoped filters in `pyproject.toml`. The proper fix — migrate to the structured wait-strategy API (`HttpWaitStrategy` / `LogMessageWaitStrategy`) — has a TODO breadcrumb in `tests/conftest.py` near the container fixtures.

**Known follow-up (recorded, not blocking):**

- Coverage on `neo4j_backend.py` shows as 14% in the unit-test report because the integration tests that exercise it run in a separate CI job whose coverage isn't aggregated. Aggregating would raise the threshold meaningfully. Out of scope for Phase 2; revisit at Phase 6 alongside the rest of the CI work.

## Phase 3 entry points

When the next session opens, start here:

| Where | Why |
|---|---|
| `docs/PROJECT_CONTEXT.md` (this file) | The fast-onboarding read |
| `docs/architecture.md` | Layering contract; `models` and `rag` rows describe the Phase-3 boundaries |
| `docs/kg.md` | What the KG layer stores and how to query it — Phase 3 consumes `cascading_risk` + `subgraph` for KG-context features |
| `argus/platform_core/kg/base.py` | The `KGBackend` Protocol the predictive head will call to enrich features |
| `argus/platform_core/models/` (currently a skeleton) | Where the evidential head, the `UncertainPrediction` schema, and the calibration utilities will land |
| `argus/domain_packs/supply_chain/data/schemas.py` | The four supply-chain entities the features layer will encode |

**Phase 3 acceptance criteria (proposed, refine when the phase opens):**

- `UncertainPrediction` schema (frozen Pydantic) carrying point + band + attribution
- Baseline tabular heads (LightGBM, XGBoost) wired through a uniform model `Protocol`
- Evidential regression / classification head (Normal-Inverse-Gamma or equivalent) producing calibrated uncertainty
- Cross-modal fusion stub that combines tabular features with KG-context features (`RiskPath` + induced subgraph stats)
- Calibration evaluation utilities (reliability diagram, ECE)
- Updated `docs/architecture.md`, this file, and a `docs/models.md` at phase close, `v0.3.0` tag

## Locked-in decisions

| Area | Decision | Why |
|---|---|---|
| Python target | 3.11 + 3.12 (CI matrix) | Forward-compat coverage without paying for 3.10 back-compat |
| Repo | github.com/argus-engine/argus-ai | Org repo signals project, not personal experiment |
| Distribution / import | `argus-risk` on PyPI, import as `argus` | `argus` import name was the user's pick; PyPI name disambiguates |
| Kaggle auth | `~/.kaggle/kaggle.json` | Kaggle's canonical path; CI secret-to-file friendly |
| GPU target | NVIDIA CUDA 12.x | User has the hardware; gpu Docker variant + compose profile |
| Phase 1 deadline | **2026-05-29** | KTP application target |
| Schemas approved | `Decimal` money, six-value `OrderStatus`, opaque `entities_mentioned: list[str]`, `raw` on all four entities | Red-lined explicitly during Task #8 — see commit `c6db7bb` |
| Deferred from Phase 1 | `UncertainPrediction` schema (→ Phase 3), `AuthProvider` stub (→ Phase 5+), Terraform resources (→ Phase 6), `LLMProvider` (→ Phase 4), KG queries (→ Phase 2), models (→ Phase 3) | Right scope for two-week deadline |
| KG node + edge taxonomy | Seven `NodeType`s (`SUPPLIER`/`PRODUCT`/`REGION`/`ORDER`/`SHIPMENT`/`CUSTOMER`/`EVENT_SIGNAL`) and ten `EdgeType`s | Spans physical actors, goods, geography, and external signals; first-class derived nodes for queryability — see `docs/kg.md` |
| Edge orientation | FK direction, not impact direction | Disruption propagates by walking the graph bidirectionally; both backends' BFS does so explicitly |
| Adapter counters seam | `KGAdapter.counters() -> Mapping[str, int]` + `IngestionReport.adapter_counters: dict[str, int]` | Pack-specific diagnostic counts without coupling `platform_core` to pack concepts |
| Coverage gate threshold | `fail_under = 83` (Phase 2 close) | Current measured unit-test coverage is 83.5%; gate is a regression-catcher, not aspirational |
| Deferred from Phase 2 | `UncertainPrediction` (→ Phase 3), Phase-3 predictive head, integration-coverage aggregation, structured-wait-strategy migration for testcontainers fixtures (→ when upstream deprecation forces it) | Scope discipline at phase boundaries |

Full decisions ledger in `memory/project_phase1_decisions.md`.

## Key architectural choices (so far)

| Choice | One-line rationale |
|---|---|
| `argus/` is the python package; `platform_core/` and `domain_packs/` sit inside it | Matches decision A (import as `argus`); keeps the package surface coherent |
| Connectors return `Iterator[RawRecord]` with a `.batched(n)` helper | Stream-by-default; batch when you need to; decision D |
| Every record is **frozen Pydantic, tz-aware, `extra="forbid"`** | Mutations and silent schema drift are review-blockers |
| Loaders are thin **column-mapping** functions over connectors | When DataCo / GDELT / EDGAR rename a column, fix at one site |
| `data/sources/` lives **inside** the pack (`data/`), not at repo root | All data-layer concerns for a pack in one tree; small expansion of brief flagged in commit |
| **Money is `Decimal`**, never float | Audit-traceable accounting precision |
| `RawRecord.raw` field carried on every entity | Audit trail beats memory overhead in this domain |
| KG enforces FK integrity, not Pydantic | Order + shipment streams arrive out of order |
| KG `upsert_*` merge semantics binding on every backend | Type-mismatch raises; properties merge per key with incoming overriding; `source_refs` union with first-seen order; identical contract across NetworkX + Neo4j |
| KG BFS traverses both edge directions | Edges encode FK direction; risk propagates either way. APOC's `relationshipFilter=""` (or `"TYPE\|TYPE"`, no `>` / `<`) gives the same bidirectional semantics on Neo4j |
| `Subgraph` is induced, not spanning-tree | RAG (Phase 4) needs every edge between collected nodes for grounding, not just BFS-traversed ones |
| Supply-chain adapter is stateful per build | Mention-resolution scans entities seen so far; caller-side ordering contract: Suppliers → Orders → Shipments → EventSignals |
| Mention resolution: skip + count, no placeholder nodes | Visibility via `IngestionReport.adapter_counters["unresolved_mentions"]` keeps the graph clean of synthetic noise |
| APOC required on Neo4j; `make_backend` falls back to NetworkX on bare install | Lazy-import keeps `argus-risk` importable without `[kg]` extras; clear `RuntimeError` if Neo4j is up but APOC is missing |
| Decimal stored as `str` in KG node properties | Neo4j driver rejects `Decimal`; round-trippable as `Decimal(s)` on read; precision preserved |
| `.partial` + `os.replace` atomic rename for every downloaded file | Same-filesystem atomic on POSIX *and* Windows; no half-written files |
| `.complete` marker per source directory | Whole-source idempotency in one `stat()` call |
| Token-bucket rate limiter with injectable `now`/`sleep` | Real SEC 10 req/s ceiling honored; tests verify without sleeping |
| SEC User-Agent resolution: explicit arg → `ARGUS_EDGAR_USER_AGENT` → default | SEC requires identification; env-var override for collaborators |
| GDELT scope **bounded**: 1-week window × four supply-chain themes | Full GKG is terabytes; bounded subset documented in `docs/data_sources.md` |
| EDGAR sample **bounded**: 6 fixed CIKs × (1 × 10-K + 3 × 8-K) | ~24 documents; small, refreshable, representative |
| Configs in YAML, never hardcoded | `pydantic-settings` reads them; decision E |
| Three-tier resolution pattern (explicit → env → default) | Reused for User-Agent; will be reused for LLMProvider in Phase 4 |

## Working conventions

These are non-negotiable for any AI assistant operating on this repo:

- **Phase-by-phase execution.** Don't scaffold everything at once. For each phase: (1) plan, (2) clarifying questions, (3) small commits, (4) tests alongside, (5) docs updated.
- **Checkpoint pauses.** Phase 1 plan paused for review at the end of Day-3 module-skeleton work (Task #4), at the schema red-line (Task #7→#8), and will pause again at the end of Phase-1 polish (Task #12). Don't push through silently.
- **Schema red-line process.** Net-new Pydantic schemas are presented as a **draft PR for red-line** before committing. Walk through contested decisions with `AskUserQuestion`; commit only after explicit answers.
- **Read-code discipline.** Memory records are claims, not truth. Before recommending from memory (file paths, function names, flag values), `grep` to verify they exist. Memory is frozen at write time; the code is authoritative now.
- **Small commits, conventional commits.** Each commit is a self-contained unit with a clear scope; commit messages explain *why* alongside *what*.
- **Tests alongside code.** Coverage target is 80%+; CI report-only in Phase 1, gating from Phase 2. New code lands with its tests in the same commit.
- **Mocks at the boundary, not in the middle.** Mock the LLM provider, the Kaggle client, `httpx`. Don't mock the function under test.
- **CI never hits live APIs.** Every external dep (Kaggle, GDELT, SEC, OpenAI eventually) has a `Protocol`-style seam and is fully mocked in tests.
- **`make check` is the contract.** Lint (ruff) + typecheck (mypy strict) + tests (pytest) all green before any commit lands.
- **SPDX header on every source file.** `# SPDX-License-Identifier: Apache-2.0` at the top of every `.py`, `.md`, `.yaml`, `.toml`, `.sh`. Pre-commit hook enforces; `tests/fixtures/**` is exempt.
- **NO attribution to Claude / Claude Code / Anthropic.** **Standing rule, top priority.** Never in commit trailers, file comments, markdown docs, git metadata, or anywhere else. All work is authored by Soheil Jafarifard Bidgoli `<soheiljafarifard@gmail.com>`. See `memory/feedback_no_attribution.md`.
- **Never auto-push, never auto-create remote.** The local repo is the source of truth; remote setup is a deliberate manual step the user controls.

## Key files to read first

If you have **two minutes**, read these in order:

1. `README.md` — pitch, mermaid diagram, quickstart, design principles
2. `docs/architecture.md` — layering contract, plugin boundaries, sequence diagram
3. `docs/data_sources.md` — bounded scope for DataCo / GDELT / EDGAR; idempotency contracts
4. `docs/responsible_ai.md` — intended use, limitations, governance
5. `pyproject.toml` — packaging, deps, tool config

If you have **ten minutes**, also read:

6. `argus/platform_core/ingestion/base.py` — the canonical "schema + ABC + helper" pattern; everything else mimics it
7. `argus/domain_packs/supply_chain/data/schemas.py` — the canonical "frozen Pydantic with validators + derived properties" pattern
8. `argus/domain_packs/supply_chain/data/sources/_http.py` + `_paths.py` — the resumable-download primitives shared by Kaggle / GDELT / EDGAR

If you have **half an hour**, run `make install && make check` and skim the test files (`tests/**/test_*.py`) — they are the most accurate documentation of how the public API is meant to be used.

## AI memory layout

Persistent memory lives at `~/.claude/projects/<this-project>/memory/`:

| File | Type | What's in it |
|---|---|---|
| `MEMORY.md` | index | One-line pointers to every memory file |
| `user_role.md` | user | Identity, KTP context, expectations |
| `project_argus.md` | project | Platform overview |
| `project_phase1_decisions.md` | project | All Phase-1 locked decisions |
| `feedback_working_style.md` | feedback | Phase-by-phase, small commits, plan before code |
| `feedback_no_attribution.md` | feedback | **Standing rule** — no Claude / Anthropic / AI attribution anywhere |

When the conversation resumes in a future session, the assistant reads `MEMORY.md` plus this document, and is on its feet in under a minute.

## Phase 1 closeout

**Tag:** `v0.1.0` (annotated). **Test suite:** 233 passing, ~4s, zero live-API calls.

| Category | Delivered |
|---|---|
| Packaging | hatchling, prod + 5 optional extras (`ml`, `kg`, `rag`, `streamlit`, `supply-chain`, `all`), `dev` extra, ruff + mypy strict + pytest + coverage + bandit configured in `pyproject.toml` |
| Docs (recruiter surface) | `README.md` (pitch + mermaid + quickstart + roadmap), `CONTRIBUTING.md`, `docs/architecture.md`, `docs/responsible_ai.md`, `docs/data_sources.md`, `docs/PROJECT_CONTEXT.md` (this file) |
| Pre-commit | ruff, mypy (project venv), conventional-pre-commit (commit-msg), SPDX header checker, whitespace / EOF / large-file / private-key sanity |
| Ingestion | `Connector` ABC + `RawRecord` / `RecordBatch` / `RecordStream` / `ConnectorConfig`, three concrete connectors (`StructuredCSVConnector`, `TextDocumentConnector`, `TimeSeriesConnector`), full test coverage |
| Supply-chain pack | `Order` / `Supplier` / `Shipment` / `EventSignal` schemas (red-lined and approved), loaders, hand-crafted fixtures, source downloaders with resumable-download contracts and bounded-scope GDELT / EDGAR subsets |
| CI | GitHub Actions: lint / typecheck / test (Py 3.11 + 3.12 matrix) / security (bandit gates, pip-audit advisory) / docker-build (multi-arch, auto-skip-until-Dockerfile) |
| Docker | Multi-stage Dockerfile with `cpu`, `gpu` (nvidia/cuda 12.4.1), and `streamlit` targets, non-root argus user (UID 1000), HEALTHCHECK on `/health`, comprehensive `.dockerignore` |
| Compose | `api` (cpu) / `api-gpu` (gpu) / `neo4j` (5.20 + APOC pre-installed) / `streamlit` services on a named network, `--profile gpu` swap, committed `.env` activates cpu by default |
| API | FastAPI `/health` placeholder with typed `HealthResponse`, OpenAPI docs at `/docs` |
| Frontend | Streamlit placeholder that probes `/health` and renders the response |
| CLI | `argus version` + `argus serve` subcommands, both surfacing in `argus --help` |
| Infra stubs | `infra/terraform/` with real `versions.tf` + `variables.tf` + `terraform.tfvars.example` plus documented Phase-6 stubs for `main.tf` / `network.tf` / `compute.tf` / `data.tf` / `iam.tf` / `outputs.tf` |
| Author identity | Every commit authored + committed by **Soheil Jafarifard Bidgoli `<soheiljafarifard@gmail.com>`**; zero Claude / Anthropic / AI attribution anywhere in tree or history |

**Deferred to later phases (intentional, on-record):**
- `UncertainPrediction` schema → Phase 3
- `LLMProvider` Protocol and prompt assets → Phase 4
- `AuthProvider` and HITL surfaces → Phase 5
- Coverage gating (currently report-only) → flips on at Phase 2 open
- pip-audit gating (currently advisory) → Phase 6
- Image digest pins (currently `MAJOR.MINOR.PATCH` tags) → Phase 6
- Terraform resource declarations → Phase 6

## Phase-closeout checklist

At the end of each phase, before tagging the release:

- [ ] Update **this document** (status table, "where we are now", new architectural choices, new locked decisions)
- [ ] Update `README.md` roadmap status (phase moves from "in progress" → "complete")
- [ ] Update `docs/architecture.md` to reflect the phase's as-built state
- [ ] Verify `make check` is green on a clean clone
- [ ] Tag the release (e.g. `v0.1.0-phase1`)
- [ ] Move next phase's tasks into the TaskList for the new session
