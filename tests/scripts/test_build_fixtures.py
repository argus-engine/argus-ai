# SPDX-License-Identifier: Apache-2.0
"""Tests for ``scripts/build_fixtures.py``.

Deterministic sampling is the load-bearing property — the same input
plus the same seed must produce byte-identical output. The CLI smoke
tests use synthetic CSVs under ``tmp_path`` so no real download is
required.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from scripts.build_fixtures import app, sample_csv


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_csv(path: Path, *, n_rows: int, header: tuple[str, ...] = ("a", "b")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    lines.extend(f"row{i},{i * 10}" for i in range(n_rows))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestSampleCsv:
    def test_writes_header_and_n_rows(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        dst = tmp_path / "out.csv"
        _make_csv(src, n_rows=20)
        rows = sample_csv(src, dst, n=5, seed=1)
        assert rows == 5
        lines = dst.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "a,b"
        assert len(lines) == 6  # header + 5 rows

    def test_sample_smaller_than_source(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        dst = tmp_path / "out.csv"
        _make_csv(src, n_rows=3)
        rows = sample_csv(src, dst, n=10, seed=42)
        assert rows == 3

    def test_empty_source_writes_only_header(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        dst = tmp_path / "out.csv"
        _make_csv(src, n_rows=0)
        rows = sample_csv(src, dst, n=10, seed=42)
        assert rows == 0
        assert dst.read_text(encoding="utf-8").rstrip("\n") == "a,b"

    def test_truly_empty_file_returns_zero(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        src.write_text("", encoding="utf-8")
        dst = tmp_path / "out.csv"
        assert sample_csv(src, dst, n=10, seed=42) == 0

    def test_deterministic_same_seed_same_output(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        _make_csv(src, n_rows=50)
        dst_a = tmp_path / "out_a.csv"
        dst_b = tmp_path / "out_b.csv"
        sample_csv(src, dst_a, n=10, seed=7)
        sample_csv(src, dst_b, n=10, seed=7)
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_different_seeds_diverge(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        _make_csv(src, n_rows=50)
        dst_a = tmp_path / "out_a.csv"
        dst_b = tmp_path / "out_b.csv"
        sample_csv(src, dst_a, n=10, seed=1)
        sample_csv(src, dst_b, n=10, seed=2)
        assert dst_a.read_bytes() != dst_b.read_bytes()

    def test_creates_destination_parent_directory(self, tmp_path: Path) -> None:
        src = tmp_path / "src.csv"
        _make_csv(src, n_rows=3)
        dst = tmp_path / "nested" / "deep" / "out.csv"
        sample_csv(src, dst, n=2, seed=42)
        assert dst.exists()


class TestBuildFixturesCli:
    def test_no_inputs_logs_hint_and_exits_zero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "data"
        output = tmp_path / "fixtures"
        # No dataco/ subdir at all
        result = runner.invoke(
            app,
            [
                "--source-dir",
                str(source),
                "--output-dir",
                str(output),
            ],
        )
        assert result.exit_code == 0, result.output

    def test_processes_dataco_orders_when_present(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "data"
        dataco_dir = source / "dataco"
        _make_csv(dataco_dir / "orders.csv", n_rows=50)
        output = tmp_path / "fixtures"

        result = runner.invoke(
            app,
            [
                "--source-dir",
                str(source),
                "--output-dir",
                str(output),
                "--sample-size",
                "10",
            ],
        )
        assert result.exit_code == 0, result.output
        derived = output / "dataco_orders.csv"
        assert derived.exists()
        # Header + 10 sampled rows
        assert len(derived.read_text(encoding="utf-8").splitlines()) == 11

    def test_processes_multiple_dataco_files(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "data"
        dataco_dir = source / "dataco"
        _make_csv(dataco_dir / "orders.csv", n_rows=20)
        _make_csv(dataco_dir / "suppliers.csv", n_rows=20)
        output = tmp_path / "fixtures"

        result = runner.invoke(
            app,
            [
                "--source-dir",
                str(source),
                "--output-dir",
                str(output),
                "--sample-size",
                "5",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (output / "dataco_orders.csv").exists()
        assert (output / "dataco_suppliers.csv").exists()

    def test_seed_round_trip_deterministic(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "data"
        dataco_dir = source / "dataco"
        _make_csv(dataco_dir / "orders.csv", n_rows=100)
        output_a = tmp_path / "a"
        output_b = tmp_path / "b"

        for output in (output_a, output_b):
            runner.invoke(
                app,
                [
                    "--source-dir",
                    str(source),
                    "--output-dir",
                    str(output),
                    "--sample-size",
                    "10",
                    "--seed",
                    "99",
                ],
            )
        assert (output_a / "dataco_orders.csv").read_bytes() == (
            output_b / "dataco_orders.csv"
        ).read_bytes()

    def test_custom_sample_size_respected(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "data"
        dataco_dir = source / "dataco"
        _make_csv(dataco_dir / "orders.csv", n_rows=200)
        output = tmp_path / "fixtures"

        runner.invoke(
            app,
            [
                "--source-dir",
                str(source),
                "--output-dir",
                str(output),
                "--sample-size",
                "25",
            ],
        )
        lines = (output / "dataco_orders.csv").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 26  # header + 25
