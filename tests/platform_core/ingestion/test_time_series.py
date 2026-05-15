# SPDX-License-Identifier: Apache-2.0
"""Tests for :class:`TimeSeriesConnector`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from argus.platform_core.ingestion.base import Modality
from argus.platform_core.ingestion.time_series import (
    TimeSeriesConfig,
    TimeSeriesConnector,
)


@pytest.fixture
def shipments_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ingestion" / "time_series" / "shipments.csv"


@pytest.fixture
def naive_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ingestion" / "time_series" / "naive_timestamps.csv"


class TestTimeSeriesConfig:
    def test_value_columns_required_non_empty(self, shipments_csv: Path) -> None:
        with pytest.raises(ValidationError):
            TimeSeriesConfig(
                name="ts",
                source="ts",
                data_path=shipments_csv,
                timestamp_column="timestamp",
                value_columns=[],
            )


class TestTimeSeriesConnector:
    def _config(
        self,
        path: Path,
        *,
        entity: str | None = "supplier_id",
        values: list[str] | None = None,
    ) -> TimeSeriesConfig:
        return TimeSeriesConfig(
            name="ts",
            source="shipments",
            data_path=path,
            timestamp_column="timestamp",
            value_columns=values or ["units_shipped", "delay_minutes"],
            entity_column=entity,
        )

    def test_pulls_every_row_as_a_record(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv))
        records = list(connector.pull())
        assert len(records) == 4

    def test_modality_is_time_series(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv))
        assert connector.modality is Modality.TIME_SERIES
        assert all(r.modality is Modality.TIME_SERIES for r in connector.pull())

    def test_record_id_combines_entity_and_timestamp(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv))
        records = list(connector.pull())
        assert records[0].record_id == "SUP001@2024-01-15T08:00:00+00:00"
        assert records[1].record_id == "SUP002@2024-01-15T09:00:00+00:00"

    def test_record_id_falls_back_to_row_index_without_entity(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv, entity=None))
        records = list(connector.pull())
        assert records[0].record_id.startswith("row000000@")
        assert records[3].record_id.startswith("row000003@")

    def test_timestamp_is_tz_aware_on_record(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv))
        records = list(connector.pull())
        assert records[0].timestamp == datetime(2024, 1, 15, 8, 0, tzinfo=UTC)
        assert records[3].timestamp == datetime(2024, 1, 15, 11, 0, tzinfo=UTC)

    def test_payload_shape(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv))
        first = next(iter(connector.pull()))
        assert first.payload == {
            "timestamp_str": "2024-01-15T08:00:00+00:00",
            "entity": "SUP001",
            "values": {"units_shipped": "100", "delay_minutes": "15"},
        }

    def test_naive_timestamps_get_utc_attached(self, naive_csv: Path) -> None:
        connector = TimeSeriesConnector(
            TimeSeriesConfig(
                name="ts",
                source="prices",
                data_path=naive_csv,
                timestamp_column="timestamp",
                value_columns=["price"],
                entity_column=None,
            )
        )
        records = list(connector.pull())
        assert records[0].timestamp is not None
        assert records[0].timestamp.tzinfo is UTC

    def test_missing_value_column_raises(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(
            self._config(shipments_csv, values=["units_shipped", "nope"])
        )
        with pytest.raises(ValueError, match="missing required columns"):
            list(connector.pull())

    def test_missing_timestamp_column_raises(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(
            TimeSeriesConfig(
                name="ts",
                source="shipments",
                data_path=shipments_csv,
                timestamp_column="nope",
                value_columns=["units_shipped"],
            )
        )
        with pytest.raises(ValueError, match="missing required columns"):
            list(connector.pull())

    def test_missing_entity_column_raises(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv, entity="nope"))
        with pytest.raises(ValueError, match="missing required columns"):
            list(connector.pull())

    def test_empty_timestamp_value_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "empty_ts.csv"
        path.write_text("timestamp,price\n,42.0\n", encoding="utf-8")
        connector = TimeSeriesConnector(
            TimeSeriesConfig(
                name="ts",
                source="prices",
                data_path=path,
                timestamp_column="timestamp",
                value_columns=["price"],
            )
        )
        with pytest.raises(ValueError, match="empty timestamp column"):
            list(connector.pull())

    def test_batchable(self, shipments_csv: Path) -> None:
        connector = TimeSeriesConnector(self._config(shipments_csv))
        batches = list(connector.pull().batched(3))
        assert [len(b) for b in batches] == [3, 1]
