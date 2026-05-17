# SPDX-License-Identifier: Apache-2.0
"""Construct a :class:`KGBackend` implementation from a backend name.

The factory is the seam between configuration (``configs/default.yaml``'s
``kg.backend`` key, or the ``ARGUS_KG_BACKEND`` environment variable) and
the concrete implementations. Caller code asks for a backend by name and
gets back something that satisfies the :class:`KGBackend` Protocol —
without importing either concrete class directly.

The Neo4j implementation lands in Task #3; until then,
``make_backend("neo4j", ...)`` raises :class:`NotImplementedError` with
a clear pointer so callers fail loudly instead of silently falling back
to a different backend.
"""

from __future__ import annotations

from argus.platform_core.kg.base import KGBackend, KGBackendConfig
from argus.platform_core.kg.networkx_backend import NetworkXBackend

_SUPPORTED: tuple[str, ...] = ("networkx",)
"""Backend names this factory currently knows how to construct."""


def make_backend(name: str, config: KGBackendConfig) -> KGBackend:
    """Return the :class:`KGBackend` implementation matching ``name``.

    Args:
        name: Backend identifier. Currently supports ``"networkx"``;
            ``"neo4j"`` is reserved and raises until Task #3 lands.
        config: Backend configuration. The NetworkX implementation
            ignores Neo4j-specific fields; the Neo4j implementation
            will require them.

    Raises:
        NotImplementedError: When ``name`` names a backend whose
            implementation has not landed yet (currently ``"neo4j"``).
        ValueError: When ``name`` is not recognised at all.
    """
    if name == "networkx":
        return NetworkXBackend(config)
    if name == "neo4j":
        raise NotImplementedError(
            "Neo4jBackend lands in Phase 2 Task #3 — until then, "
            "select 'networkx' or wait for the next checkpoint."
        )
    raise ValueError(f"unknown KG backend {name!r}; supported names: {', '.join(_SUPPORTED)}")


__all__ = ["make_backend"]
