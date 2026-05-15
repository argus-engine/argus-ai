# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``argus`` CLI entry point.

The recruiter-touchable surface is ``pip install argus-risk && argus --help``,
so the structure of ``--help`` and the behavior of ``version`` are worth
locking in.
"""

from __future__ import annotations

from typer.testing import CliRunner

from argus import __version__
from argus.cli import app


def test_help_lists_both_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # Header pitch should appear
    assert "Argus" in result.output
    # Both subcommands surface
    assert "version" in result.output
    assert "serve" in result.output


def test_version_prints_installed_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])
    # `no_args_is_help=True` makes the CLI exit non-zero when invoked
    # without a subcommand — that's the contract Typer offers.
    assert result.exit_code != 0
    assert "version" in result.output
    assert "serve" in result.output


def test_serve_help_shows_options() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    for flag in ("--host", "--port", "--reload", "--log-level"):
        assert flag in result.output


def test_version_help_shows_description() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version", "--help"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()
