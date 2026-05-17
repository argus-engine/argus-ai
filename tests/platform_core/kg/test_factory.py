# SPDX-License-Identifier: Apache-2.0
"""Contract tests for :func:`make_backend`."""

from __future__ import annotations

import importlib.util

import pytest

from argus.platform_core.kg import (
    KGBackend,
    KGBackendConfig,
    NetworkXBackend,
    make_backend,
)

# Probe for the neo4j driver without importing it — needed so the
# missing-driver test only runs on a bare install, and the driver-
# present test only runs when the [kg] extra is installed.
_NEO4J_DRIVER_AVAILABLE = importlib.util.find_spec("neo4j") is not None


class TestMakeBackend:
    def test_networkx_returns_networkx_backend(self) -> None:
        backend = make_backend("networkx", KGBackendConfig(name="t"))
        assert isinstance(backend, NetworkXBackend)

    def test_networkx_result_satisfies_kgbackend_protocol(self) -> None:
        backend = make_backend("networkx", KGBackendConfig(name="t"))
        assert isinstance(backend, KGBackend)

    def test_unknown_name_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown KG backend"):
            make_backend("janusgraph", KGBackendConfig(name="t"))

    @pytest.mark.skipif(
        _NEO4J_DRIVER_AVAILABLE,
        reason="needs the neo4j driver to be absent (bare [dev] install)",
    )
    def test_neo4j_without_driver_raises_import_error(self) -> None:
        with pytest.raises(ImportError, match=r"argus-risk\[kg\]"):
            make_backend(
                "neo4j",
                KGBackendConfig(name="t", neo4j_uri="bolt://localhost:7687"),
            )

    @pytest.mark.skipif(
        not _NEO4J_DRIVER_AVAILABLE,
        reason="needs the neo4j driver to be installed ([dev,kg])",
    )
    def test_neo4j_with_driver_requires_uri(self) -> None:
        with pytest.raises(ValueError, match="neo4j_uri"):
            make_backend("neo4j", KGBackendConfig(name="t"))
