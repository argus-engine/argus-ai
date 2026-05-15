<!-- SPDX-License-Identifier: Apache-2.0 -->
# Data sources

This document is the contract between `scripts/download_data.py` and the
upstream world. It exists because the supply-chain pack consumes three
real public datasets that each have non-trivial licensing terms, scope
decisions, and rate-limit constraints. Anyone refreshing the local data
should read this first.

## Sources at a glance

| Source | What we use | Scope | Licensing |
|---|---|---|---|
| **DataCo Smart Supply Chain** | Structured orders, suppliers, shipments | The full Kaggle dataset | Kaggle dataset, per the publisher's Kaggle page terms — non-redistributable |
| **GDELT 2.0 GKG** | Global event signals filtered to supply-chain themes | **Bounded subset** — see below | CC BY 4.0, attribution required |
| **SEC EDGAR** | 10-K and 8-K filings for a small fixed sample of supplier-relevant US-listed companies | **Bounded sample** — see below | Public domain, with the SEC's published usage limits |

## DataCo (Kaggle)

DataCo Smart Supply Chain is the canonical tabular dataset for supply-chain
ML research: order line items, customer attributes, shipping mode, delivery
status, and (synthetic) supplier mapping. We download it via the Kaggle API.

**What you need:**
- A Kaggle account
- `~/.kaggle/kaggle.json` containing your API token (see the README quickstart)

**Idempotency contract:**
- Files land in `data/dataco/` with a `.complete` marker on success
- Downloads stream into `<name>.partial` and are atomically renamed to `<name>`
  on completion, so an interrupted run can be re-invoked safely — the partial
  file is overwritten on retry, not appended to
- Re-running on a fully-completed directory is a no-op; pass `--force` to
  re-download

**Redistribution:** The DataCo CSVs themselves are **never committed to the
repo**. Only the fixtures derived from them (~100 rows under `tests/fixtures/`)
are committed, and those are reviewed for any sensitive content before commit.

## GDELT 2.0 GKG — bounded subset

GDELT's full Global Knowledge Graph (GKG) corpus is in the **terabyte** range
and grows by ~96 files per day (a new 15-minute slot every 15 minutes). We do
**not** download the full corpus. We download a deliberate subset.

**Subset definition:**

- **Time window:** A fixed one-week window centered on a historical reference
  date (`2024-01-15` to `2024-01-22` inclusive by default). Override at the
  CLI with `--gdelt-start` / `--gdelt-end`. One week × 96 slots/day ≈ 672
  files; ~10 MB compressed each, so ≈ 7 GB total before filtering.
- **Theme filter:** Every record's `V2Themes` column is parsed; we keep rows
  whose themes intersect the following set:
  - `SUPPLY_CHAIN`
  - `INFRASTRUCTURE_BAD_CONDITIONS`
  - `NATURAL_DISASTER`
  - `ECON_TRADE`
- **Output:** Filtered rows are concatenated into a single
  `data/gdelt/gkg_<start>_to_<end>.csv`, typically a few MB after filtering.

**Why these themes:**
The GDELT theme taxonomy is enormous (thousands of tags). The four above are
chosen because they map directly to the supply-chain disruption signals our
predictive heads will consume in later phases:

- `SUPPLY_CHAIN` — explicit chain-of-custody disruption mentions
- `INFRASTRUCTURE_BAD_CONDITIONS` — port closures, road blockages, plant
  shutdowns
- `NATURAL_DISASTER` — weather and seismic events that disrupt physical flow
- `ECON_TRADE` — tariffs, sanctions, trade-policy events

This set is small enough that we can audit every theme, and broad enough that
real disruption events almost always carry at least one. We will revisit if
later phases show coverage gaps.

**Idempotency contract:**
- Per-slot files are downloaded to `data/gdelt/raw/<slot>.csv.zip.partial`,
  atomically renamed on success
- Slots already present (full file, no `.partial`) are skipped
- After all slots are present, the filtered output file is written and a
  `.complete` marker is touched
- `--force` re-runs the filter step but does not re-download slots

**Attribution:** GDELT data is CC BY 4.0. Any derived artifact that ships
this data must credit "The GDELT Project" — covered by `docs/responsible_ai.md`.

## SEC EDGAR — bounded sample

The SEC's EDGAR system hosts filings for tens of thousands of registrants.
We do **not** scrape it broadly. We download a deliberate small sample.

**Sample definition:**

A fixed list of six US-listed companies whose business is directly relevant
to supply-chain disruption modeling:

| Ticker | CIK | Why included |
|---|---|---|
| WMT (Walmart) | 0000104169 | Largest US retailer; bellwether for demand-side disruption |
| FDX (FedEx) | 0001048911 | Express logistics; air-freight disruption proxy |
| UPS | 0001090727 | Ground and air logistics; complements FedEx |
| COST (Costco) | 0000909832 | Wholesale; long-cycle inventory exposure |
| TGT (Target) | 0000027419 | Mid-market retail; container-shipping exposed |
| CAT (Caterpillar) | 0000018230 | Industrial supply-chain bellwether; global manufacturing |

For each company we download:
- The `submissions` JSON index (small, summarizes recent filings)
- The primary document of the **most recent 10-K** and **the three most
  recent 8-K** filings

This is ≈ 24 documents total — bounded, refreshable in seconds, and
representative of the filing types that drive disruption signals.

**Rate limit:** SEC publishes a **10 requests per second** limit. The
download client uses a token bucket capped at `10 req/s` and serializes
requests across the whole sample, so the actual rate is well below the
limit. Every request carries the User-Agent header in the form **the SEC
requires** (a project name plus a contact email):

```
Argus Platform soheiljafarifard@gmail.com
```

This is configurable via the `ARGUS_EDGAR_USER_AGENT` environment variable
if a different identity is needed.

**Idempotency contract:**
- Per-document files land in `data/edgar/<cik>_<ticker>/<filing_type>/<accession>.html`
- Already-present files are skipped (idempotent re-run)
- `--force` re-downloads
- Failed downloads leave a `.partial`; the next run replaces it

**Compliance:** EDGAR data is in the public domain. The SEC asks downloaders
to:

1. Send a User-Agent identifying who they are — we do
2. Stay under 10 req/s — we do, capped well below
3. Not parallelize requests (single HTTP connection) — we use one client

## Refresh cadence

These downloads are not run automatically. Refresh is a manual operation:

```bash
python scripts/download_data.py --source all
```

In CI, network access is disabled and the scripts are not invoked. Tests
mock the HTTP layer (see `tests/.../test_*.py`).

## What ships in the repo

| Path | Status |
|---|---|
| `data/` | **gitignored** — never committed; populated locally by `download_data.py` |
| `tests/fixtures/supply_chain/` | **committed** — ~100-row deterministic samples plus hand-crafted edge cases, produced by `scripts/build_fixtures.py` from the downloaded corpora |

The fixtures are derived from real downloads via a seeded, deterministic
sampling pass so re-running `build_fixtures.py` on the same downloaded data
produces the same fixture bytes.
