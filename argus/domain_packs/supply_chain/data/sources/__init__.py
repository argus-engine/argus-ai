# SPDX-License-Identifier: Apache-2.0
"""Source-acquisition primitives for the supply-chain domain pack.

This subpackage knows how to fetch the three reference sources documented in
``docs/data_sources.md``:

- DataCo Smart Supply Chain (Kaggle) via ``kaggle.py``
- GDELT 2.0 GKG (public URLs) via ``gdelt.py``
- SEC EDGAR (public API) via ``edgar.py``

Shared helpers — a rate-limited HTTP client and atomic-write utilities —
live in ``_http.py`` and ``_paths.py``. ``scripts/download_data.py`` is a
thin CLI shim over the functions exported here.

Architectural note: ``sources/`` is a small expansion of the brief's
``data/`` directory. ``data/`` already owns schemas and loaders; adding
source acquisition keeps everything related to the pack's data layer in one
place rather than scattering download logic across the repo.
"""

from argus.domain_packs.supply_chain.data.sources._http import (
    RateLimitedClient,
    TokenBucket,
)
from argus.domain_packs.supply_chain.data.sources._paths import (
    atomic_write_bytes,
    clear_complete_marker,
    is_complete,
    mark_complete,
)

__all__ = [
    "RateLimitedClient",
    "TokenBucket",
    "atomic_write_bytes",
    "clear_complete_marker",
    "is_complete",
    "mark_complete",
]
