# SPDX-License-Identifier: Apache-2.0
"""Filesystem helpers for resumable, idempotent downloads.

Two contracts:

1. **Atomic rename.** Every file lands as ``<name>.partial`` first, then is
   renamed to ``<name>`` only after a successful write. An interrupted run
   leaves a ``.partial`` behind, which the next run overwrites — so we never
   see a half-written file masquerading as a complete one.

2. **``.complete`` marker.** Each source directory carries a sentinel file
   (``.complete``) that is only touched after every file the source needs is
   present. Idempotent re-runs check the marker first and skip the source
   entirely when it's set. ``--force`` clears the marker before starting.

``os.replace`` is atomic on the same filesystem on POSIX and Windows
(see PEP 428 / `os.replace` docs), so the rename is safe across both.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

_COMPLETE_MARKER = ".complete"


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` via a ``.partial`` + atomic rename.

    Returns the final path. Caller is responsible for ``path.parent``
    existing; no recursive mkdir here, so the surrounding code is explicit
    about what directories it creates.
    """
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_bytes(data)
    os.replace(partial, path)
    return path


def atomic_write_stream(path: Path, chunks: Iterable[bytes]) -> Path:
    """Stream chunks into ``path.partial``, then atomic-rename to ``path``.

    Use this when the payload is large enough that buffering the full bytes
    in memory would be wasteful (e.g., GDELT slot files at ~10 MB each).
    """
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("wb") as fh:
        for chunk in chunks:
            fh.write(chunk)
    os.replace(partial, path)
    return path


def is_complete(source_dir: Path) -> bool:
    """Whether ``source_dir`` has been marked complete on a previous run."""
    return (source_dir / _COMPLETE_MARKER).exists()


def mark_complete(source_dir: Path) -> None:
    """Touch the ``.complete`` sentinel inside ``source_dir``.

    Idempotent; safe to call repeatedly.
    """
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / _COMPLETE_MARKER).touch()


def clear_complete_marker(source_dir: Path) -> None:
    """Remove the ``.complete`` sentinel, so the next download re-runs.

    Used by the CLI's ``--force`` path. Idempotent; a missing marker is not
    an error.
    """
    marker = source_dir / _COMPLETE_MARKER
    if marker.exists():
        marker.unlink()


__all__ = [
    "atomic_write_bytes",
    "atomic_write_stream",
    "clear_complete_marker",
    "is_complete",
    "mark_complete",
]
