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
| **1. Foundations** | Repo skeleton, packaging, CI, ingestion ABCs, supply-chain schemas, Docker, docs | **in progress** — Task #10 (CI) next |
| **2. Knowledge layer** | Neo4j construction from supply-chain pack, KG queries, NetworkX fallback, first baseline model (LightGBM) | not started |
| **3. Modeling & RAG** | Evidential uncertainty heads, multi-modal fusion, RAG with grounding rubric, fabrication check | not started |
| **4. Human in the loop** | Streamlit reviewer dashboard, structured disagreement capture, active-learning feedback into Phase 3 models | not started |
| **5. Multi-cloud + observability** | Terraform GCP + AWS, multi-arch image push, OpenTelemetry traces, evaluation harness | not started |
| **6. Release & community** | Tag 1.0, contribution onboarding, docs site, security review, examples gallery | not started |

Each phase ends with a tagged release, refreshed `docs/architecture.md`, and runnable acceptance criteria.

## Where we are now

**Phase 1, ~73% through.** Tasks #1–#9 done, #10–#12 pending.

Phase-1 task ledger (matches the TaskList in-session):

1. ✅ Packaging foundation (pyproject.toml, LICENSE, .gitignore, .python-version)
2. ✅ README with pitch + mermaid diagram + quickstart
3. ✅ `docs/architecture.md` + `docs/responsible_ai.md` + `CONTRIBUTING.md`
4. ✅ Full module skeleton with phase-boundary docstrings
5. ✅ Pre-commit + conventional commits + SPDX header check + Makefile
6. ✅ `Connector` ABC + Pydantic record schemas
7. ✅ Three concrete connectors: `StructuredCSVConnector`, `TextDocumentConnector`, `TimeSeriesConnector`
8. ✅ Supply-chain schemas (`Order`/`Supplier`/`Shipment`/`EventSignal`) + loaders + tests *(draft-PR red-line process)*
9. ✅ `scripts/download_data.py` + `scripts/build_fixtures.py` *(DataCo, bounded GDELT, EDGAR sample)*
10. ⬜ GitHub Actions CI **← next**
11. ⬜ Dockerfile (multi-stage, CPU + CUDA 12.x `gpu` target) + `docker-compose.yml`
12. ⬜ Polish + quickstart verification

**State as of the last commit:** 22 commits on `main`, **223 tests passing in 3.82s**, zero live-API calls in CI.

## Locked-in decisions

| Area | Decision | Why |
|---|---|---|
| Python target | 3.11 + 3.12 (CI matrix) | Forward-compat coverage without paying for 3.10 back-compat |
| Repo | github.com/argus-ai/platform | Org repo signals project, not personal experiment |
| Distribution / import | `argus-risk` on PyPI, import as `argus` | `argus` import name was the user's pick; PyPI name disambiguates |
| Kaggle auth | `~/.kaggle/kaggle.json` | Kaggle's canonical path; CI secret-to-file friendly |
| GPU target | NVIDIA CUDA 12.x | User has the hardware; gpu Docker variant + compose profile |
| Phase 1 deadline | **2026-05-29** | KTP application target |
| Schemas approved | `Decimal` money, six-value `OrderStatus`, opaque `entities_mentioned: list[str]`, `raw` on all four entities | Red-lined explicitly during Task #8 — see commit `c6db7bb` |
| Deferred from Phase 1 | `UncertainPrediction` schema (→ Phase 3), `AuthProvider` stub (→ Phase 4+), Terraform resources (→ Phase 5), `LLMProvider` (→ Phase 3), KG queries, models | Right scope for two-week deadline |

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
| `.partial` + `os.replace` atomic rename for every downloaded file | Same-filesystem atomic on POSIX *and* Windows; no half-written files |
| `.complete` marker per source directory | Whole-source idempotency in one `stat()` call |
| Token-bucket rate limiter with injectable `now`/`sleep` | Real SEC 10 req/s ceiling honored; tests verify without sleeping |
| SEC User-Agent resolution: explicit arg → `ARGUS_EDGAR_USER_AGENT` → default | SEC requires identification; env-var override for collaborators |
| GDELT scope **bounded**: 1-week window × four supply-chain themes | Full GKG is terabytes; bounded subset documented in `docs/data_sources.md` |
| EDGAR sample **bounded**: 6 fixed CIKs × (1 × 10-K + 3 × 8-K) | ~24 documents; small, refreshable, representative |
| Configs in YAML, never hardcoded | `pydantic-settings` reads them; decision E |
| Three-tier resolution pattern (explicit → env → default) | Reused for User-Agent; will be reused for LLMProvider in Phase 3 |

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

## Phase-closeout checklist

At the end of each phase, before tagging the release:

- [ ] Update **this document** (status table, "where we are now", new architectural choices, new locked decisions)
- [ ] Update `README.md` roadmap status (phase moves from "in progress" → "complete")
- [ ] Update `docs/architecture.md` to reflect the phase's as-built state
- [ ] Verify `make check` is green on a clean clone
- [ ] Tag the release (e.g. `v0.1.0-phase1`)
- [ ] Move next phase's tasks into the TaskList for the new session
