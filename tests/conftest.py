# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for the Argus test suite.

Fixtures specific to a layer live alongside that layer's tests; only
truly cross-cutting fixtures (e.g., temporary directories, frozen-time
clocks) belong here.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the committed test fixtures directory."""
    return Path(__file__).parent / "fixtures"
