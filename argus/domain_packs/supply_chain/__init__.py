# SPDX-License-Identifier: Apache-2.0
"""Supply chain disruption forecasting — the reference domain pack.

This pack fuses three sources:

- **DataCo Smart Supply Chain** (Kaggle): structured orders, suppliers, shipments
- **GDELT 2.0** (public URL): global event signals indicating disruption risk
- **SEC EDGAR** (free API): supplier 10-K / 8-K filings indicating financial stress

It normalizes them into shared Pydantic schemas (`Order`, `Supplier`, `Shipment`,
`EventSignal`) defined in `data/schemas.py`, exposes loaders that compose the
platform's ingestion connectors (`data/loaders.py`), and — in later phases —
ships pack-tuned prompts, predictive heads, and an evaluation harness.

**Phase 1 surface:** Pydantic schemas + loaders that produce them from the three
sources, plus a test fixture set in `tests/fixtures/supply_chain/`.

**Install extras:** ``pip install argus-risk[supply-chain]`` pulls the Kaggle
client, SEC EDGAR downloader, and HTTP dependencies this pack needs.
"""
