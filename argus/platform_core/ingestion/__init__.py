# SPDX-License-Identifier: Apache-2.0
"""Ingestion: external sources → normalized `RawRecord` stream.

This is the lowest layer of `platform_core`. Every connector implements the
`Connector` ABC (`base.py`) and yields a `RecordStream` of records annotated
with modality (`structured`, `text`, `time_series`) and a `source` provenance
tag.

**Phase 1 surface (this phase):**

- `Connector` ABC with batching helper
- `RawRecord`, `RecordBatch`, `RecordStream`, `ConnectorConfig`, `Modality`
- Concrete connectors: `StructuredCSVConnector`, `TextDocumentConnector`,
  `TimeSeriesConnector` (Task #7)

**Out of scope this phase:** streaming connectors (Kafka, Kinesis), online-
learning sources, and PII-redacting wrappers — those land in later phases. The
interface shape here is designed to accommodate them without breaking changes.
"""

from argus.platform_core.ingestion.base import (
    Connector,
    ConnectorConfig,
    Modality,
    RawRecord,
    RecordBatch,
    RecordStream,
    parse_timestamp,
)
from argus.platform_core.ingestion.structured import (
    StructuredCSVConfig,
    StructuredCSVConnector,
)
from argus.platform_core.ingestion.text import (
    TextDocumentConfig,
    TextDocumentConnector,
)

__all__ = [
    "Connector",
    "ConnectorConfig",
    "Modality",
    "RawRecord",
    "RecordBatch",
    "RecordStream",
    "StructuredCSVConfig",
    "StructuredCSVConnector",
    "TextDocumentConfig",
    "TextDocumentConnector",
    "parse_timestamp",
]
