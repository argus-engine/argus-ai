# SPDX-License-Identifier: Apache-2.0
"""Construct a :class:`KGBackend` implementation from a backend name.

The factory is the seam between configuration (``configs/default.yaml``'s
``kg.backend`` key, or the ``ARGUS_KG_BACKEND`` environment variable) and
the concrete implementations. Caller code asks for a backend by name and
gets back something that satisfies the :class:`KGBackend` Protocol —
without importing either concrete class directly.

The Neo4j implementation lives behind a lazy import inside this
factory: importing :mod:`argus.platform_core.kg` does not pull in the
``neo4j`` driver, so the ``[kg]`` extra stays opt-in for users who
only need the in-process :class:`NetworkXBackend` fallback.
"""

from __future__ import annotations

from argus.platform_core.kg.base import KGBackend, KGBackendConfig
from argus.platform_core.kg.networkx_backend import NetworkXBackend

_SUPPORTED: tuple[str, ...] = ("networkx", "neo4j")
"""Backend names this factory knows how to construct."""


def make_backend(name: str, config: KGBackendConfig) -> KGBackend:
    """Return the :class:`KGBackend` implementation matching ``name``.

    Args:
        name: Backend identifier. Supports ``"networkx"`` (always
            available, in-process) and ``"neo4j"`` (requires the
            ``[kg]`` extra and a reachable Neo4j with APOC).
        config: Backend configuration. ``NetworkXBackend`` ignores
            Neo4j-specific fields; ``Neo4jBackend`` requires
            ``neo4j_uri`` at minimum.

    Raises:
        ImportError: When ``name == "neo4j"`` and the ``neo4j`` driver
            is not installed.
        ValueError: When ``name`` is not recognised.
    """
    if name == "networkx":
        return NetworkXBackend(config)
    if name == "neo4j":
        # Lazy import: the [kg] extra is opt-in. Users on a base install
        # who only need NetworkX should never trip over the neo4j driver
        # not being present.
        from argus.platform_core.kg.neo4j_backend import Neo4jBackend

        return Neo4jBackend(config)
    raise ValueError(f"unknown KG backend {name!r}; supported names: {', '.join(_SUPPORTED)}")


__all__ = ["make_backend"]
