# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``scripts/download_data.py`` CLI.

The actual download functions are patched at the script's module so we
verify dispatch, argument parsing, and the dry-run path without ever
touching the live APIs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from scripts import download_data
from scripts.download_data import Source, app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def stubbed_downloaders(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Replace each downloader on the script module with a recording mock."""
    mocks: dict[str, MagicMock] = {
        "dataco": MagicMock(return_value=Path("data/dataco")),
        "gdelt": MagicMock(return_value=Path("data/gdelt/out.csv")),
        "edgar": MagicMock(return_value=Path("data/edgar")),
    }
    monkeypatch.setattr(download_data, "download_dataco", mocks["dataco"])
    monkeypatch.setattr(download_data, "download_gdelt_gkg_subset", mocks["gdelt"])
    monkeypatch.setattr(download_data, "download_edgar_sample", mocks["edgar"])
    return mocks


class TestSourceSelection:
    def test_default_runs_all_three(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(app, ["--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        stubbed_downloaders["dataco"].assert_called_once()
        stubbed_downloaders["gdelt"].assert_called_once()
        stubbed_downloaders["edgar"].assert_called_once()

    def test_only_kaggle(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(app, ["--source", "kaggle", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        stubbed_downloaders["dataco"].assert_called_once()
        stubbed_downloaders["gdelt"].assert_not_called()
        stubbed_downloaders["edgar"].assert_not_called()

    def test_only_gdelt(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(app, ["--source", "gdelt", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        stubbed_downloaders["gdelt"].assert_called_once()
        stubbed_downloaders["dataco"].assert_not_called()
        stubbed_downloaders["edgar"].assert_not_called()

    def test_only_edgar(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(app, ["--source", "edgar", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        stubbed_downloaders["edgar"].assert_called_once()
        stubbed_downloaders["dataco"].assert_not_called()
        stubbed_downloaders["gdelt"].assert_not_called()


class TestDryRun:
    def test_dry_run_invokes_nothing(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(app, ["--dry-run", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        stubbed_downloaders["dataco"].assert_not_called()
        stubbed_downloaders["gdelt"].assert_not_called()
        stubbed_downloaders["edgar"].assert_not_called()

    def test_dry_run_with_specific_source(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            app,
            ["--source", "kaggle", "--dry-run", "--output-dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        for mock in stubbed_downloaders.values():
            mock.assert_not_called()


class TestForcePropagation:
    def test_force_flag_passed_through(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--source",
                "kaggle",
                "--force",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        call = stubbed_downloaders["dataco"].call_args
        assert call.kwargs["force"] is True

    def test_force_default_is_false(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        runner.invoke(app, ["--source", "kaggle", "--output-dir", str(tmp_path)])
        call = stubbed_downloaders["dataco"].call_args
        assert call.kwargs["force"] is False


class TestGdeltWindowOverrides:
    def test_default_window_is_utc(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        runner.invoke(app, ["--source", "gdelt", "--output-dir", str(tmp_path)])
        call = stubbed_downloaders["gdelt"].call_args
        start = call.kwargs["start"]
        end = call.kwargs["end"]
        assert start.tzinfo is not None
        assert end.tzinfo is not None
        # Default in module is 2024-01-15 → 2024-01-22
        assert start == datetime(2024, 1, 15, tzinfo=UTC)
        assert end == datetime(2024, 1, 22, tzinfo=UTC)

    def test_overridden_window_propagates_with_utc(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--source",
                "gdelt",
                "--gdelt-start",
                "2024-06-01T00:00:00",
                "--gdelt-end",
                "2024-06-08T00:00:00",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        call = stubbed_downloaders["gdelt"].call_args
        assert call.kwargs["start"] == datetime(2024, 6, 1, tzinfo=UTC)
        assert call.kwargs["end"] == datetime(2024, 6, 8, tzinfo=UTC)


class TestOutputDirRouting:
    def test_per_source_subdirs(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        runner.invoke(app, ["--output-dir", str(tmp_path)])
        assert stubbed_downloaders["dataco"].call_args.args[0] == tmp_path / "dataco"
        assert stubbed_downloaders["gdelt"].call_args.args[0] == tmp_path / "gdelt"
        assert stubbed_downloaders["edgar"].call_args.args[0] == tmp_path / "edgar"

    def test_output_dir_is_created(
        self,
        runner: CliRunner,
        stubbed_downloaders: dict[str, MagicMock],
        tmp_path: Path,
    ) -> None:
        new_dir = tmp_path / "deep" / "nested"
        runner.invoke(app, ["--source", "edgar", "--output-dir", str(new_dir)])
        assert new_dir.exists()
        # Verify the fixture was wired and the EDGAR downloader was reached.
        stubbed_downloaders["edgar"].assert_called_once()


class TestSourceEnum:
    def test_enum_round_trip(self) -> None:
        assert Source("all") is Source.ALL
        assert Source("kaggle") is Source.KAGGLE
        assert Source("gdelt") is Source.GDELT
        assert Source("edgar") is Source.EDGAR
