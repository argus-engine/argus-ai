# SPDX-License-Identifier: Apache-2.0
"""Ingestion: external sources → normalized `RawRecord` stream.

This is the lowest layer of `platform_core`. Every connector implements the
`Connector` ABC (`base.py`) and yields an `Iterator[RawRecord]` annotated with
modality (`structured`, `text`, `time_series`) and a `source` provenance tag.

**Phase 1 surface (this phase):**

- `Connector` ABC with batching helper
- `RawRecord`, `RecordBatch`, `ConnectorConfig` Pydantic schemas
- Concrete connectors: `StructuredCSVConnector`, `TextDocumentConnector`,
  `TimeSeriesConnector`

**Out of scope this phase:** streaming connectors (Kafka, Kinesis), online-learning
sources, and PII-redacting wrappers — those land in later phases. The interface
shape here is designed to accommodate them without breaking changes.
"""
