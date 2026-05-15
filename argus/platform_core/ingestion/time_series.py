# SPDX-License-Identifier: Apache-2.0
"""TimeSeriesConnector — emit one :class:`RawRecord` per time-series row.

The structured connector treats a CSV as a heterogeneous table; this one
treats it as one or more time series, identified by an optional ``entity``
column and pinned to a parsed, timezone-aware timestamp on every record.

Values are kept as strings in the payload. Type coercion (to float, int,
etc.) lives in ``argus.platform_core.features`` where domain encoders can
decide what each column means.

Per-row record IDs are built from the entity and the raw timestamp string
so the same (entity, timestamp) combination is never silently aliased.
The connector assumes one observation per ``(entity, timestamp)`` pair —
collisions raise downstream during ingestion into the KG, not here, because
the connector cannot know whether duplicates indicate genuine sensor
multiplexing or a malformed source.
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


class TimeSeriesConfig(ConnectorConfig):
    """Configuration for :class:`TimeSeriesConnector`."""

    data_path: Path = Field(..., description="Path to the CSV file to read.")
    timestamp_column: str = Field(
        ...,
        min_length=1,
        description="Column containing the row's timestamp.",
    )
    value_columns: list[str] = Field(
        ...,
        min_length=1,
        description="Columns whose values are the time-series measurements.",
    )
    entity_column: str | None = Field(
        default=None,
        description=(
            "Optional column identifying which entity (supplier, sensor, etc.) "
            "the row belongs to. When ``None``, the row index drives the id."
        ),
    )
    timestamp_format: str | None = Field(
        default=None,
        description=(
            "Optional ``strptime`` format string for the timestamp column. "
            "When ``None``, ISO 8601 is used."
        ),
    )
    encoding: str = Field(default="utf-8")
    delimiter: str = Field(default=",", min_length=1, max_length=1)


class TimeSeriesConnector(Connector[TimeSeriesConfig]):
    """Emit one :class:`RawRecord` per row of a time-series CSV."""

    @property
    def modality(self) -> Modality:
        return Modality.TIME_SERIES

    def pull(self) -> RecordStream:
        return RecordStream(self._iter_rows())

    def _iter_rows(self) -> Iterator[RawRecord]:
        cfg = self.config
        with cfg.data_path.open(encoding=cfg.encoding, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=cfg.delimiter)
            fieldnames = reader.fieldnames or []
            if not fieldnames:
                return
            self._validate_columns(fieldnames)

            for row_idx, row in enumerate(reader):
                raw_ts = (row.get(cfg.timestamp_column) or "").strip()
                if not raw_ts:
                    raise ValueError(
                        f"row {row_idx} in {cfg.data_path} has empty timestamp "
                        f"column {cfg.timestamp_column!r}"
                    )
                timestamp = parse_timestamp(raw_ts, cfg.timestamp_format)

                entity: str | None = None
                if cfg.entity_column:
                    entity = (row.get(cfg.entity_column) or "").strip() or None

                record_id = (
                    f"{entity}@{raw_ts}"
                    if entity is not None
                    else f"row{row_idx:06d}@{raw_ts}"
                )

                payload: dict[str, object] = {
                    "timestamp_str": raw_ts,
                    "entity": entity,
                    "values": {col: row[col] for col in cfg.value_columns},
                }

                yield self._make_record(
                    record_id=record_id,
                    payload=payload,
                    timestamp=timestamp,
                )

    def _validate_columns(self, fieldnames: list[str]) -> None:
        cfg = self.config
        required = {cfg.timestamp_column, *cfg.value_columns}
        if cfg.entity_column:
            required.add(cfg.entity_column)
        missing = sorted(required - set(fieldnames))
        if missing:
            raise ValueError(
                f"CSV at {cfg.data_path} is missing required columns: "
                f"{missing}. Available columns: {fieldnames}"
            )


__all__ = ["TimeSeriesConfig", "TimeSeriesConnector"]
