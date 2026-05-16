# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for the Argus test suite.

Fixtures specific to a layer live alongside that layer's tests; only
truly cross-cutting fixtures (e.g., temporary directories, frozen-time
clocks, environment-stability shims) belong here.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the committed test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _disable_cli_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force plain (uncoloured) CLI output for cross-platform test stability.

    Typer (and the Rich renderer it pulls in) emit ANSI colour escapes when
    they detect a colour-capable terminal. On Linux CI runners and most
    Linux developer terminals this is the default, so ``CliRunner`` captures
    output like ``\\x1b[1m--host\\x1b[0m`` instead of plain ``--host``.
    Windows terminals typically don't trigger the colour path, so substring
    assertions on ``--help`` output pass locally and break on CI.

    The fix is the cross-stack opt-out standard from https://no-color.org —
    setting ``NO_COLOR`` to any non-empty value tells Typer / Rich / Click
    to skip colour, and ``CliRunner`` then captures the exact same plain
    text on every platform.

    Autouse + function-scoped so every test gets a clean env without
    needing to wire the fixture into its signature. Setting it for non-CLI
    tests is harmless — they don't read it.
    """
    monkeypatch.setenv("NO_COLOR", "1")
