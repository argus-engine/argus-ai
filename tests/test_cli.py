# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``argus`` CLI entry point.

The recruiter-touchable surface is ``pip install argus-risk && argus --help``,
so the structure of ``--help`` and the behavior of ``version`` are worth
locking in.

Substring assertions on CLI output go through :func:`_plain` so they don't
break on Linux/CI where Typer's Rich renderer wraps tokens in ANSI escape
sequences (e.g. ``\\x1b[1m--host\\x1b[0m``). The Windows path is uncoloured
and ``_plain`` is a no-op there, so the same assertions pass on every
platform.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from argus import __version__
from argus.cli import app

# Match every ANSI escape sequence Rich/Typer can emit in help output:
# CSI introducer (\x1b[) followed by parameter bytes (0-9, ;, ?, etc.) and a
# final byte in the ASCII range 0x40..0x7E. Covers SGR (colour, bold) and
# cursor / mode control codes.
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain(text: str) -> str:
    """Strip ANSI escape sequences so substring assertions are colour-agnostic."""
    return _ANSI_RE.sub("", text)


def test_help_lists_both_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = _plain(result.output)
    # Header pitch should appear
    assert "Argus" in out
    # Both subcommands surface
    assert "version" in out
    assert "serve" in out


def test_version_prints_installed_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in _plain(result.output)


def test_no_args_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])
    # `no_args_is_help=True` makes the CLI exit non-zero when invoked
    # without a subcommand — that's the contract Typer offers.
    assert result.exit_code != 0
    out = _plain(result.output)
    assert "version" in out
    assert "serve" in out


def test_serve_help_shows_options() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    out = _plain(result.output)
    for flag in ("--host", "--port", "--reload", "--log-level"):
        assert flag in out


def test_version_help_shows_description() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version", "--help"])
    assert result.exit_code == 0
    assert "version" in _plain(result.output).lower()
