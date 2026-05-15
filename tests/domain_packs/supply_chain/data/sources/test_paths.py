# SPDX-License-Identifier: Apache-2.0
"""Tests for the atomic-write and ``.complete`` marker helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from argus.domain_packs.supply_chain.data.sources._paths import (
    atomic_write_bytes,
    atomic_write_stream,
    clear_complete_marker,
    is_complete,
    mark_complete,
)


class TestAtomicWriteBytes:
    def test_writes_file_and_no_partial_remains(self, tmp_path: Path) -> None:
        dest = tmp_path / "data.csv"
        result = atomic_write_bytes(dest, b"hello,world\n")
        assert result == dest
        assert dest.read_bytes() == b"hello,world\n"
        assert not dest.with_suffix(".csv.partial").exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "data.csv"
        dest.write_bytes(b"stale")
        atomic_write_bytes(dest, b"fresh")
        assert dest.read_bytes() == b"fresh"

    def test_overwrites_stale_partial_from_previous_run(self, tmp_path: Path) -> None:
        dest = tmp_path / "data.csv"
        partial = dest.with_suffix(".csv.partial")
        partial.write_bytes(b"interrupted")
        atomic_write_bytes(dest, b"clean")
        assert dest.read_bytes() == b"clean"
        assert not partial.exists()


class TestAtomicWriteStream:
    def test_streams_chunks_into_final_path(self, tmp_path: Path) -> None:
        dest = tmp_path / "stream.csv"
        chunks = [b"alpha\n", b"beta\n", b"gamma\n"]
        atomic_write_stream(dest, iter(chunks))
        assert dest.read_bytes() == b"alpha\nbeta\ngamma\n"
        assert not dest.with_suffix(".csv.partial").exists()

    def test_handles_empty_stream(self, tmp_path: Path) -> None:
        dest = tmp_path / "empty.csv"
        atomic_write_stream(dest, iter([]))
        assert dest.exists()
        assert dest.read_bytes() == b""


class TestCompleteMarker:
    def test_round_trip(self, tmp_path: Path) -> None:
        assert is_complete(tmp_path) is False
        mark_complete(tmp_path)
        assert is_complete(tmp_path) is True
        clear_complete_marker(tmp_path)
        assert is_complete(tmp_path) is False

    def test_mark_complete_is_idempotent(self, tmp_path: Path) -> None:
        mark_complete(tmp_path)
        mark_complete(tmp_path)  # second call is a no-op
        assert is_complete(tmp_path) is True

    def test_clear_complete_marker_when_missing_is_noop(self, tmp_path: Path) -> None:
        clear_complete_marker(tmp_path)  # never marked complete
        assert is_complete(tmp_path) is False

    def test_mark_complete_creates_parent_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        mark_complete(nested)
        assert is_complete(nested) is True


class TestPartialFilenamePattern:
    @pytest.mark.parametrize(
        ("name", "expected_partial"),
        [
            ("data.csv", "data.csv.partial"),
            ("data.csv.zip", "data.csv.zip.partial"),
            ("filing.html", "filing.html.partial"),
        ],
    )
    def test_partial_extension_added(
        self, tmp_path: Path, name: str, expected_partial: str
    ) -> None:
        dest = tmp_path / name
        atomic_write_bytes(dest, b"x")
        assert dest.exists()
        assert not (tmp_path / expected_partial).exists()
