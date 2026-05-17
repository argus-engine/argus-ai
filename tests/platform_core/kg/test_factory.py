# SPDX-License-Identifier: Apache-2.0
"""Contract tests for :func:`make_backend`."""

from __future__ import annotations

import pytest

from argus.platform_core.kg import (
    KGBackend,
    KGBackendConfig,
    NetworkXBackend,
    make_backend,
)


class TestMakeBackend:
    def test_networkx_returns_networkx_backend(self) -> None:
        backend = make_backend("networkx", KGBackendConfig(name="t"))
        assert isinstance(backend, NetworkXBackend)

    def test_networkx_result_satisfies_kgbackend_protocol(self) -> None:
        backend = make_backend("networkx", KGBackendConfig(name="t"))
        assert isinstance(backend, KGBackend)

    def test_neo4j_raises_not_implemented_until_task_three(self) -> None:
        with pytest.raises(NotImplementedError, match="Task #3"):
            make_backend("neo4j", KGBackendConfig(name="t"))

    def test_unknown_name_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown KG backend"):
            make_backend("janusgraph", KGBackendConfig(name="t"))
