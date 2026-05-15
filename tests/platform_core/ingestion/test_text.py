# SPDX-License-Identifier: Apache-2.0
"""Tests for :class:`TextDocumentConnector`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from argus.platform_core.ingestion.base import Modality
from argus.platform_core.ingestion.text import (
    TextDocumentConfig,
    TextDocumentConnector,
)


@pytest.fixture
def text_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ingestion" / "text"


class TestTextDocumentConfig:
    def test_chunk_size_must_be_positive(self, text_dir: Path) -> None:
        with pytest.raises(ValidationError):
            TextDocumentConfig(
                name="news",
                source="news",
                root_path=text_dir,
                chunk_size=0,
            )

    def test_overlap_must_be_smaller_than_chunk_size(self, text_dir: Path) -> None:
        with pytest.raises(ValidationError, match="chunk_overlap"):
            TextDocumentConfig(
                name="news",
                source="news",
                root_path=text_dir,
                chunk_size=100,
                chunk_overlap=100,
            )


class TestTextDocumentConnector:
    def test_directory_walk_returns_matching_files(self, text_dir: Path) -> None:
        connector = TextDocumentConnector(
            TextDocumentConfig(name="news", source="news", root_path=text_dir)
        )
        records = list(connector.pull())
        # not_a_txt.md is skipped by the *.txt pattern
        ids = [r.record_id for r in records]
        assert ids == ["article_001.txt", "article_002.txt"]

    def test_modality_is_text(self, text_dir: Path) -> None:
        connector = TextDocumentConnector(
            TextDocumentConfig(name="news", source="news", root_path=text_dir)
        )
        assert connector.modality is Modality.TEXT
        assert all(r.modality is Modality.TEXT for r in connector.pull())

    def test_payload_contains_file_metadata(self, text_dir: Path) -> None:
        connector = TextDocumentConnector(
            TextDocumentConfig(name="news", source="news", root_path=text_dir)
        )
        first = next(iter(connector.pull()))
        assert first.payload["filename"] == "article_001.txt"
        assert first.payload["chunk_index"] == 0
        assert first.payload["total_chunks"] == 1
        assert "Port congestion in Long Beach" in first.payload["text"]

    def test_single_file_root_path(self, text_dir: Path) -> None:
        single = text_dir / "article_002.txt"
        connector = TextDocumentConnector(
            TextDocumentConfig(name="news", source="news", root_path=single)
        )
        records = list(connector.pull())
        assert len(records) == 1
        assert records[0].record_id == "article_002.txt"
        assert "Penang" in records[0].payload["text"]

    def test_custom_file_pattern(self, text_dir: Path) -> None:
        connector = TextDocumentConnector(
            TextDocumentConfig(
                name="news",
                source="news",
                root_path=text_dir,
                file_pattern="*.md",
            )
        )
        records = list(connector.pull())
        assert [r.record_id for r in records] == ["not_a_txt.md"]

    def test_missing_root_path_raises(self, tmp_path: Path) -> None:
        connector = TextDocumentConnector(
            TextDocumentConfig(name="x", source="x", root_path=tmp_path / "nope")
        )
        with pytest.raises(FileNotFoundError):
            list(connector.pull())

    def test_chunking_emits_expected_chunks(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.txt"
        path.write_text("0123456789ABCDEF", encoding="utf-8")  # 16 chars
        connector = TextDocumentConnector(
            TextDocumentConfig(
                name="chunked",
                source="chunked",
                root_path=path,
                chunk_size=5,
                chunk_overlap=0,
            )
        )
        records = list(connector.pull())
        # 16 / 5 = 3 full + 1 partial → 4 chunks: "01234", "56789", "ABCDE", "F"
        assert [r.payload["text"] for r in records] == ["01234", "56789", "ABCDE", "F"]
        assert [r.payload["chunk_index"] for r in records] == [0, 1, 2, 3]
        assert all(r.payload["total_chunks"] == 4 for r in records)
        assert [r.record_id for r in records] == [
            "doc.txt#0",
            "doc.txt#1",
            "doc.txt#2",
            "doc.txt#3",
        ]

    def test_chunking_with_overlap(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.txt"
        path.write_text("abcdefghij", encoding="utf-8")  # 10 chars
        connector = TextDocumentConnector(
            TextDocumentConfig(
                name="overlapped",
                source="overlapped",
                root_path=path,
                chunk_size=4,
                chunk_overlap=2,
            )
        )
        records = list(connector.pull())
        # stride = 2, chunks at offsets 0, 2, 4, 6, 8 → "abcd", "cdef", "efgh", "ghij", "ij"
        assert [r.payload["text"] for r in records] == [
            "abcd",
            "cdef",
            "efgh",
            "ghij",
            "ij",
        ]

    def test_empty_file_yields_nothing_when_chunking(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.txt"
        path.write_text("", encoding="utf-8")
        connector = TextDocumentConnector(
            TextDocumentConfig(
                name="empty",
                source="empty",
                root_path=path,
                chunk_size=10,
            )
        )
        assert list(connector.pull()) == []

    def test_empty_file_yields_one_record_without_chunking(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.txt"
        path.write_text("", encoding="utf-8")
        connector = TextDocumentConnector(
            TextDocumentConfig(name="empty", source="empty", root_path=path)
        )
        records = list(connector.pull())
        assert len(records) == 1
        assert records[0].payload["text"] == ""
        assert records[0].payload["total_chunks"] == 1

    def test_records_are_batchable(self, text_dir: Path) -> None:
        connector = TextDocumentConnector(
            TextDocumentConfig(name="news", source="news", root_path=text_dir)
        )
        batches = list(connector.pull().batched(1))
        assert [len(b) for b in batches] == [1, 1]
