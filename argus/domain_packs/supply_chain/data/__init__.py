# SPDX-License-Identifier: Apache-2.0
"""Supply-chain data layer: schemas + loaders.

This is the boundary between the raw source data (DataCo CSVs, GDELT events,
SEC EDGAR filings) and everything downstream. Downstream code never touches
the raw shape — it consumes the normalized Pydantic schemas declared here.

**Modules:**

- `schemas.py` — `Order`, `Supplier`, `Shipment`, `EventSignal` (lands in
  Day 7 of Phase 1, presented as a draft for red-line before merge)
- `loaders.py` — functions composing `argus.platform_core.ingestion`
  connectors into normalized objects, plus simple in-memory joiners
"""
