# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the ingestion ABCs and Pydantic schemas.

These verify the interface itself: enum values, schema immutability, the
batching helper's edge cases, and the ABC's enforcement of required methods.
Each concrete connector ships its own test file in the same directory.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from argus.platform_core.ingestion.base import (
    Connector,
    ConnectorConfig,
    Modality,
    RawRecord,
    RecordBatch,
    RecordStream,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(record_id: str = "1", *, source: str = "test_source") -> RawRecord:
    return RawRecord(
        record_id=record_id,
        source=source,
        modality=Modality.STRUCTURED,
        payload={"value": 1},
        ingested_at=datetime.now(timezone.utc),
    )


class _TestConfig(ConnectorConfig):
    """Concrete config used by the in-test connector subclass."""

    extra_field: str = "default"


class _TestConnector(Connector[_TestConfig]):
    """Minimal connector subclass for exercising the ABC contract."""

    def __init__(self, config: _TestConfig, *, count: int = 5) -> None:
        super().__init__(config)
        self._count = count

    @property
    def modality(self) -> Modality:
        return Modality.STRUCTURED

    def pull(self) -> RecordStream:
        def gen() -> Iterator[RawRecord]:
            for i in range(self._count):
                yield self._make_record(record_id=str(i), payload={"i": i})

        return RecordStream(gen())


# ---------------------------------------------------------------------------
# Modality
# ---------------------------------------------------------------------------


class TestModality:
    def test_has_three_values(self) -> None:
        assert {m.value for m in Modality} == {"structured", "text", "time_series"}

    def test_is_a_string_enum(self) -> None:
        assert Modality.STRUCTURED == "structured"
        assert Modality("text") is Modality.TEXT


# ---------------------------------------------------------------------------
# RawRecord
# ---------------------------------------------------------------------------


class TestRawRecord:
    def test_minimal_valid_record_round_trips(self) -> None:
        now = datetime.now(timezone.utc)
        rec = RawRecord(
            record_id="abc",
            source="src",
            modality=Modality.TEXT,
            payload={"k": "v"},
            ingested_at=now,
        )
        assert rec.record_id == "abc"
        assert rec.modality is Modality.TEXT
        assert rec.payload == {"k": "v"}
        assert rec.schema_version == "1"

    def test_is_frozen(self) -> None:
        rec = _record()
        with pytest.raises(ValidationError):
            rec.record_id = "tampered"  # type: ignore[misc]

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawRecord(  # type: ignore[call-arg]
                record_id="1",
                source="src",
                modality=Modality.STRUCTURED,
                payload={},
                ingested_at=datetime.now(timezone.utc),
                surprise="field",
            )

    @pytest.mark.parametrize("field", ["record_id", "source"])
    def test_string_fields_require_non_empty_value(self, field: str) -> None:
        kwargs = {
            "record_id": "x",
            "source": "src",
            "modality": Modality.STRUCTURED,
            "payload": {},
            "ingested_at": datetime.now(timezone.utc),
        }
        kwargs[field] = ""
        with pytest.raises(ValidationError):
            RawRecord(**kwargs)  # type: ignore[arg-type]

    def test_ingested_at_must_be_timezone_aware(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            RawRecord(
                record_id="x",
                source="src",
                modality=Modality.STRUCTURED,
                payload={},
                ingested_at=datetime(2026, 1, 1),  # naive  # noqa: DTZ001
            )

    def test_timestamp_must_be_timezone_aware_when_set(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            RawRecord(
                record_id="x",
                source="src",
                modality=Modality.STRUCTURED,
                payload={},
                ingested_at=datetime.now(timezone.utc),
                timestamp=datetime(2026, 1, 1),  # noqa: DTZ001
            )

    def test_provenance_joins_source_and_id(self) -> None:
        assert _record("42", source="dataco").provenance == "dataco:42"


# ---------------------------------------------------------------------------
# RecordBatch
# ---------------------------------------------------------------------------


class TestRecordBatch:
    def test_len_iter_and_bool(self) -> None:
        batch = RecordBatch(records=(_record("1"), _record("2")))
        assert len(batch) == 2
        assert [r.record_id for r in batch] == ["1", "2"]
        assert bool(batch) is True

    def test_empty_batch_is_falsy(self) -> None:
        assert bool(RecordBatch(records=())) is False

    def test_batch_id_is_unique_per_instance(self) -> None:
        a = RecordBatch(records=(_record(),))
        b = RecordBatch(records=(_record(),))
        assert a.batch_id != b.batch_id

    def test_is_frozen(self) -> None:
        batch = RecordBatch(records=(_record(),))
        with pytest.raises(ValidationError):
            batch.batch_id = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RecordStream
# ---------------------------------------------------------------------------


class TestRecordStream:
    def test_iterates_records_in_order(self) -> None:
        stream = RecordStream(iter([_record("1"), _record("2"), _record("3")]))
        assert [r.record_id for r in stream] == ["1", "2", "3"]

    def test_batched_returns_full_size_batches(self) -> None:
        stream = RecordStream(iter([_record(str(i)) for i in range(6)]))
        batches = list(stream.batched(2))
        assert [len(b) for b in batches] == [2, 2, 2]

    def test_batched_tail_batch_is_smaller(self) -> None:
        stream = RecordStream(iter([_record(str(i)) for i in range(7)]))
        batches = list(stream.batched(3))
        assert [len(b) for b in batches] == [3, 3, 1]

    def test_batched_empty_source_yields_nothing(self) -> None:
        stream = RecordStream(iter([]))
        assert list(stream.batched(4)) == []

    @pytest.mark.parametrize("invalid_size", [0, -1, -100])
    def test_batched_rejects_non_positive_size(self, invalid_size: int) -> None:
        stream = RecordStream(iter([_record()]))
        with pytest.raises(ValueError, match="positive"):
            list(stream.batched(invalid_size))

    def test_batches_preserve_record_order(self) -> None:
        records = [_record(str(i)) for i in range(5)]
        stream = RecordStream(iter(records))
        seen = [r.record_id for batch in stream.batched(2) for r in batch]
        assert seen == ["0", "1", "2", "3", "4"]


# ---------------------------------------------------------------------------
# ConnectorConfig
# ---------------------------------------------------------------------------


class TestConnectorConfig:
    def test_base_fields_required(self) -> None:
        with pytest.raises(ValidationError):
            ConnectorConfig(name="ok", source="")  # source empty

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConnectorConfig(name="ok", source="src", typo=1)  # type: ignore[call-arg]

    def test_is_frozen(self) -> None:
        cfg = _TestConfig(name="t", source="s")
        with pytest.raises(ValidationError):
            cfg.name = "tampered"  # type: ignore[misc]

    def test_subclass_inherits_base_fields(self) -> None:
        cfg = _TestConfig(name="t", source="s", extra_field="hello")
        assert cfg.name == "t"
        assert cfg.source == "s"
        assert cfg.extra_field == "hello"


# ---------------------------------------------------------------------------
# Connector ABC
# ---------------------------------------------------------------------------


class TestConnectorABC:
    def test_cannot_instantiate_abstract_base(self) -> None:
        with pytest.raises(TypeError):
            Connector(_TestConfig(name="t", source="s"))  # type: ignore[abstract]

    def test_subclass_missing_pull_cannot_instantiate(self) -> None:
        class _Bad(Connector[_TestConfig]):
            @property
            def modality(self) -> Modality:
                return Modality.STRUCTURED

        with pytest.raises(TypeError):
            _Bad(_TestConfig(name="t", source="s"))  # type: ignore[abstract]

    def test_subclass_missing_modality_cannot_instantiate(self) -> None:
        class _Bad(Connector[_TestConfig]):
            def pull(self) -> RecordStream:
                return RecordStream(iter([]))

        with pytest.raises(TypeError):
            _Bad(_TestConfig(name="t", source="s"))  # type: ignore[abstract]

    def test_working_subclass_yields_expected_records(self) -> None:
        connector = _TestConnector(_TestConfig(name="t", source="src"), count=3)
        records = list(connector.pull())
        assert [r.record_id for r in records] == ["0", "1", "2"]
        assert all(r.source == "src" for r in records)
        assert all(r.modality is Modality.STRUCTURED for r in records)

    def test_make_record_stamps_modality_and_source(self) -> None:
        connector = _TestConnector(_TestConfig(name="t", source="provenance_tag"))
        rec = next(iter(connector.pull()))
        assert rec.source == "provenance_tag"
        assert rec.modality is Modality.STRUCTURED
        assert rec.ingested_at.tzinfo is not None

    def test_pull_is_idempotent_across_calls(self) -> None:
        connector = _TestConnector(_TestConfig(name="t", source="s"), count=2)
        ids_a = [r.record_id for r in connector.pull()]
        ids_b = [r.record_id for r in connector.pull()]
        assert ids_a == ids_b

    def test_streamed_records_can_be_batched(self) -> None:
        connector = _TestConnector(_TestConfig(name="t", source="s"), count=5)
        batches = list(connector.pull().batched(2))
        assert [len(b) for b in batches] == [2, 2, 1]
