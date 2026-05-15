# SPDX-License-Identifier: Apache-2.0
"""Tests for :class:`StructuredCSVConnector`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from argus.platform_core.ingestion.base import Modality
from argus.platform_core.ingestion.structured import (
    StructuredCSVConfig,
    StructuredCSVConnector,
)


@pytest.fixture
def orders_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ingestion" / "structured" / "orders.csv"


@pytest.fixture
def bad_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ingestion" / "structured" / "bad_missing_id.csv"


@pytest.fixture
def semicolon_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ingestion" / "structured" / "semicolon_delimited.csv"


class TestStructuredCSVConfig:
    def test_minimal_valid_config(self, orders_csv: Path) -> None:
        cfg = StructuredCSVConfig(
            name="orders",
            source="dataco_orders",
            csv_path=orders_csv,
            id_column="order_id",
        )
        assert cfg.csv_path == orders_csv
        assert cfg.delimiter == ","
        assert cfg.encoding == "utf-8"
        assert cfg.timestamp_column is None

    def test_delimiter_must_be_single_char(self, orders_csv: Path) -> None:
        with pytest.raises(ValidationError):
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
                delimiter=";;",
            )


class TestStructuredCSVConnector:
    def test_pulls_every_row_as_a_record(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
            )
        )
        records = list(connector.pull())
        assert len(records) == 4
        assert [r.record_id for r in records] == [
            "ORD-1001",
            "ORD-1002",
            "ORD-1003",
            "ORD-1004",
        ]

    def test_modality_is_structured(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
            )
        )
        assert connector.modality is Modality.STRUCTURED
        first = next(iter(connector.pull()))
        assert first.modality is Modality.STRUCTURED

    def test_payload_preserves_all_columns(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
            )
        )
        first = next(iter(connector.pull()))
        assert first.payload == {
            "order_id": "ORD-1001",
            "customer_id": "C001",
            "product_id": "P-101",
            "quantity": "2",
            "unit_price": "24.99",
            "order_date": "2024-01-15T10:30:00+00:00",
            "region": "EMEA",
        }

    def test_source_propagates_to_records(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
            )
        )
        assert all(r.source == "dataco_orders" for r in connector.pull())

    def test_timestamp_column_populates_record_timestamp(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
                timestamp_column="order_date",
            )
        )
        first = next(iter(connector.pull()))
        assert first.timestamp == datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

    def test_missing_id_column_raises(self, bad_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="bad",
                source="bad_csv",
                csv_path=bad_csv,
                id_column="order_id",
            )
        )
        with pytest.raises(ValueError, match="missing required columns"):
            list(connector.pull())

    def test_missing_timestamp_column_raises(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
                timestamp_column="nope",
            )
        )
        with pytest.raises(ValueError, match="missing required columns"):
            list(connector.pull())

    def test_custom_delimiter(self, semicolon_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=semicolon_csv,
                id_column="order_id",
                delimiter=";",
            )
        )
        records = list(connector.pull())
        assert [r.record_id for r in records] == ["ORD-2001", "ORD-2002"]
        assert records[0].payload["customer_id"] == "C010"

    def test_missing_file_raises_on_pull(self, tmp_path: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="missing",
                source="dataco_orders",
                csv_path=tmp_path / "does_not_exist.csv",
                id_column="order_id",
            )
        )
        with pytest.raises(FileNotFoundError):
            list(connector.pull())

    def test_empty_file_yields_no_records(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="empty",
                source="dataco_orders",
                csv_path=empty,
                id_column="order_id",
            )
        )
        assert list(connector.pull()) == []

    def test_empty_id_column_value_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "missing_id.csv"
        path.write_text("order_id,quantity\n,5\n", encoding="utf-8")
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="missing_id",
                source="dataco_orders",
                csv_path=path,
                id_column="order_id",
            )
        )
        with pytest.raises(ValueError, match="empty id_column"):
            list(connector.pull())

    def test_batched_consumption(self, orders_csv: Path) -> None:
        connector = StructuredCSVConnector(
            StructuredCSVConfig(
                name="orders",
                source="dataco_orders",
                csv_path=orders_csv,
                id_column="order_id",
            )
        )
        batches = list(connector.pull().batched(2))
        assert [len(b) for b in batches] == [2, 2]
