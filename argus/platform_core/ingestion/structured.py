# SPDX-License-Identifier: Apache-2.0
"""StructuredCSVConnector — emit one :class:`RawRecord` per CSV row.

This is the workhorse connector for tabular sources (DataCo orders, supplier
master tables, shipment manifests). It streams rows lazily so multi-million-
row CSVs do not need to fit in memory.

Each row becomes a record whose payload is the row's column→value map. The
caller designates one column as the record identifier and may optionally
designate a timestamp column.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from pydantic import Field

from argus.platform_core.ingestion.base import (
    Connector,
    ConnectorConfig,
    Modality,
    RawRecord,
    RecordStream,
    parse_timestamp,
)


class StructuredCSVConfig(ConnectorConfig):
    """Configuration for :class:`StructuredCSVConnector`."""

    csv_path: Path = Field(..., description="Path to the CSV file to read.")
    id_column: str = Field(
        ...,
        min_length=1,
        description="Column whose value becomes the record's ``record_id``.",
    )
    timestamp_column: str | None = Field(
        default=None,
        description="Optional column to populate the record's ``timestamp`` field.",
    )
    timestamp_format: str | None = Field(
        default=None,
        description=(
            "Optional ``strptime`` format string for the timestamp column. "
            "When ``None``, ISO 8601 (``datetime.fromisoformat``) is used."
        ),
    )
    encoding: str = Field(default="utf-8")
    delimiter: str = Field(default=",", min_length=1, max_length=1)


class StructuredCSVConnector(Connector[StructuredCSVConfig]):
    """Emit one :class:`RawRecord` per row in a CSV file."""

    @property
    def modality(self) -> Modality:
        return Modality.STRUCTURED

    def pull(self) -> RecordStream:
        return RecordStream(self._iter_rows())

    def _iter_rows(self) -> Iterator[RawRecord]:
        cfg = self.config
        with cfg.csv_path.open(encoding=cfg.encoding, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=cfg.delimiter)
            fieldnames = reader.fieldnames or []
            if not fieldnames:
                return  # empty file — no header, no rows
            self._validate_columns(fieldnames)

            for row in reader:
                record_id = (row.get(cfg.id_column) or "").strip()
                if not record_id:
                    raise ValueError(
                        f"row in {cfg.csv_path} has empty id_column "
                        f"({cfg.id_column!r}); refusing to emit a record without an id"
                    )
                timestamp = None
                if cfg.timestamp_column:
                    raw_ts = (row.get(cfg.timestamp_column) or "").strip()
                    if raw_ts:
                        timestamp = parse_timestamp(raw_ts, cfg.timestamp_format)
                yield self._make_record(
                    record_id=record_id,
                    payload=dict(row),
                    timestamp=timestamp,
                )

    def _validate_columns(self, fieldnames: list[str]) -> None:
        cfg = self.config
        missing: list[str] = []
        if cfg.id_column not in fieldnames:
            missing.append(cfg.id_column)
        if cfg.timestamp_column and cfg.timestamp_column not in fieldnames:
            missing.append(cfg.timestamp_column)
        if missing:
            raise ValueError(
                f"CSV at {cfg.csv_path} is missing required columns: "
                f"{missing}. Available columns: {fieldnames}"
            )


__all__ = ["StructuredCSVConfig", "StructuredCSVConnector"]
