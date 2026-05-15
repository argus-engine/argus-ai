# SPDX-License-Identifier: Apache-2.0
"""Base contracts for the ingestion layer.

This module defines the four objects every concrete connector composes with:

- :class:`Modality` — enum tagging a record as ``structured``, ``text``, or
  ``time_series``.
- :class:`RawRecord` — the normalized, immutable payload emitted by a
  connector.
- :class:`RecordBatch` — a typed wrapper around a list of records, returned by
  the ``.batched(n)`` helper.
- :class:`RecordStream` — an iterator over ``RawRecord`` with a ``.batched(n)``
  method, so callers can switch between one-record-at-a-time and chunked
  consumption without the connector needing two methods.
- :class:`ConnectorConfig` — the Pydantic base every concrete connector
  config extends.
- :class:`Connector` — the abstract base. Every concrete connector inherits
  from it and implements ``modality`` and ``pull``.

Design notes:
- Records are **frozen** Pydantic models. The payload dict itself is not
  deep-frozen (Python doesn't), but field reassignment on the model is
  blocked. Treat the payload as immutable by convention.
- ``pull()`` is synchronous. Streaming and async connectors land in a later
  phase as a sibling ``apull()`` method; the sync surface stays the default.
- The connector is generic in its config type so static type checkers can
  follow the link from a concrete subclass to the subclass's config schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Modality(StrEnum):
    """The three input modalities Argus handles in its first phase."""

    STRUCTURED = "structured"
    TEXT = "text"
    TIME_SERIES = "time_series"


def parse_timestamp(raw: str, fmt: str | None = None) -> datetime:
    """Parse a timestamp string into a timezone-aware :class:`datetime`.

    The canonical parser for the ingestion layer — every connector that
    extracts a timestamp from string input goes through this function so the
    naive-datetime handling stays consistent across modalities.

    Args:
        raw: The raw string to parse.
        fmt: An optional :func:`datetime.strptime` format. When ``None``
            (the default), :meth:`datetime.fromisoformat` is used.

    Returns:
        A timezone-aware datetime. If the parsed value is naive, UTC is
        attached — never silently dropped on the floor.
    """
    ts = datetime.strptime(raw, fmt) if fmt else datetime.fromisoformat(raw)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


class RawRecord(BaseModel):
    """A single normalized record emitted by a :class:`Connector`.

    Fields are intentionally minimal: the connector layer is responsible for
    *normalization* (producing this shape) but not for *enrichment*
    (which happens in ``features`` and ``kg`` layers downstream).

    Provenance is carried explicitly via ``source`` plus ``record_id`` so the
    full trail can be reconstructed during audit (see
    ``docs/responsible_ai.md``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str = Field(
        ...,
        min_length=1,
        description="Identifier unique within ``source``.",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Provenance tag identifying the upstream source.",
    )
    modality: Modality = Field(
        ...,
        description="Which of the three input modalities this record carries.",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="The normalized record body. Schema is per-connector.",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="When the event the record describes occurred. Optional.",
    )
    ingested_at: datetime = Field(
        ...,
        description="UTC timestamp when this record was emitted by the connector.",
    )
    schema_version: str = Field(
        default="1",
        description="Version tag for the payload schema, bumped on breaking changes.",
    )

    @field_validator("ingested_at", "timestamp")
    @classmethod
    def _require_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("datetime fields on RawRecord must be timezone-aware")
        return value

    @property
    def provenance(self) -> str:
        """Return a stable ``source:record_id`` key suitable for joining."""
        return f"{self.source}:{self.record_id}"


class RecordBatch(BaseModel):
    """A typed wrapper around a list of records returned by ``.batched(n)``.

    The wrapper exists so batch-level metadata (size, batch identifier, future
    telemetry hooks) has a home without callers having to invent it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    records: tuple[RawRecord, ...] = Field(..., description="Records in this batch.")
    batch_id: str = Field(default_factory=lambda: uuid4().hex)

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[RawRecord]:  # type: ignore[override]
        return iter(self.records)

    def __bool__(self) -> bool:
        return bool(self.records)


class RecordStream:
    """An iterator over :class:`RawRecord` with a ``.batched(n)`` helper.

    Wraps any underlying ``Iterator[RawRecord]`` (typically a generator inside
    a connector's ``pull()`` method). The wrapper is single-pass, just like
    the underlying iterator — calling ``.batched(n)`` consumes from the same
    source, so do not iterate ``stream`` and also call ``stream.batched(n)``
    on the same instance.
    """

    __slots__ = ("_source",)

    def __init__(self, source: Iterator[RawRecord]) -> None:
        self._source = iter(source)

    def __iter__(self) -> RecordStream:
        return self

    def __next__(self) -> RawRecord:
        return next(self._source)

    def batched(self, size: int) -> Iterator[RecordBatch]:
        """Yield :class:`RecordBatch` instances of up to ``size`` records each.

        The final batch may be smaller than ``size`` if the source's length is
        not a multiple of ``size``. ``size`` must be a positive integer.
        """
        if size <= 0:
            raise ValueError(f"batch size must be positive, got {size}")
        buffer: list[RawRecord] = []
        for record in self._source:
            buffer.append(record)
            if len(buffer) >= size:
                yield RecordBatch(records=tuple(buffer))
                buffer = []
        if buffer:
            yield RecordBatch(records=tuple(buffer))


class ConnectorConfig(BaseModel):
    """Base class for connector configuration objects.

    Concrete connectors extend this with their own fields. The base requires a
    human-readable ``name`` (used in logs and metrics) and a ``source`` tag
    (propagated onto every emitted :class:`RawRecord` as provenance).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="Human-readable connector name.")
    source: str = Field(
        ...,
        min_length=1,
        description="Provenance tag stamped onto every emitted RawRecord.",
    )


ConfigT = TypeVar("ConfigT", bound=ConnectorConfig)


class Connector(ABC, Generic[ConfigT]):
    """Abstract base class for ingestion connectors.

    A connector encapsulates one external source. Every concrete subclass:

    1. Declares its ``modality`` (a :class:`Modality` value).
    2. Implements ``pull()`` to yield a :class:`RecordStream`.
    3. Accepts a config object whose type is bound to the class via ``ConfigT``.

    Connectors are designed to be stateless from the caller's perspective —
    repeated ``pull()`` calls must be safe (modulo upstream rate limits) and
    must not depend on hidden instance state set by previous invocations.
    """

    def __init__(self, config: ConfigT) -> None:
        self.config: ConfigT = config

    @property
    @abstractmethod
    def modality(self) -> Modality:
        """The :class:`Modality` of records this connector emits."""

    @abstractmethod
    def pull(self) -> RecordStream:
        """Yield records from the underlying source as a :class:`RecordStream`."""

    def _make_record(
        self,
        record_id: str,
        payload: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        schema_version: str = "1",
    ) -> RawRecord:
        """Helper for subclasses: build a :class:`RawRecord` with this connector's
        ``modality`` and ``source`` already filled in."""
        return RawRecord(
            record_id=record_id,
            source=self.config.source,
            modality=self.modality,
            payload=payload,
            timestamp=timestamp,
            ingested_at=datetime.now(UTC),
            schema_version=schema_version,
        )


__all__ = [
    "Connector",
    "ConnectorConfig",
    "Modality",
    "RawRecord",
    "RecordBatch",
    "RecordStream",
    "parse_timestamp",
]
