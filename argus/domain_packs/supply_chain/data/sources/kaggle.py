# SPDX-License-Identifier: Apache-2.0
"""DataCo Smart Supply Chain download via the Kaggle API.

This module wraps the ``kaggle`` Python client behind a thin interface so we
can:

1. Mock it at the boundary in tests (CI must never hit the live Kaggle API)
2. Apply the project's resumable-download contract — write to a sibling
   ``<dest>.partial`` directory and atomic-rename to the final ``<dest>``
   only after every file is in place
3. Carry a ``.complete`` marker so re-running on a fully-downloaded
   directory is a no-op

The default dataset slug is documented in :data:`DATACO_DATASET` and is
configurable per call. If the upstream slug changes, override at the call
site rather than hard-coding it deeper.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import structlog

from argus.domain_packs.supply_chain.data.sources._paths import (
    clear_complete_marker,
    is_complete,
    mark_complete,
)

logger = structlog.get_logger(__name__)

DATACO_DATASET = "shashwatwork/dataco-smart-supply-chain"
"""Default Kaggle dataset slug for DataCo Smart Supply Chain.

If the slug moves, the override is a single keyword argument away — see
``download_dataco``.
"""


class KaggleApiClient(Protocol):
    """Minimal surface of the Kaggle API client that this module depends on.

    Defined as a :class:`typing.Protocol` so tests can substitute a fake
    without monkey-patching the real ``kaggle`` package.
    """

    def authenticate(self) -> None:
        """Resolve credentials (usually from ``~/.kaggle/kaggle.json``)."""

    def dataset_download_files(
        self, dataset: str, *, path: str, unzip: bool = True
    ) -> None:
        """Download all files belonging to ``dataset`` into ``path``."""


def _default_client_factory() -> KaggleApiClient:
    """Construct the real ``kaggle.api`` client.

    Imported lazily so the supply-chain pack can be loaded for non-Kaggle
    workflows without the ``kaggle`` extra being installed.
    """
    from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: PLC0415

    return KaggleApi()  # type: ignore[no-any-return]  # kaggle package ships no stubs


def download_dataco(
    dest_dir: Path,
    *,
    dataset: str = DATACO_DATASET,
    force: bool = False,
    client_factory: Callable[[], KaggleApiClient] = _default_client_factory,
) -> Path:
    """Download (or skip) the DataCo dataset into ``dest_dir``.

    Idempotent: re-running on a fully-downloaded directory is a no-op.
    Resumable: download lands in ``<dest>.partial`` first and is atomic-
    renamed to ``<dest>`` only after Kaggle reports success.

    Args:
        dest_dir: Final destination directory. Created if missing.
        dataset: Kaggle dataset slug. Defaults to :data:`DATACO_DATASET`.
        force: If ``True``, ignore the ``.complete`` marker and re-download.
        client_factory: Callable producing the Kaggle API client. Override
            in tests; defaults to the real client.

    Returns:
        The path to ``dest_dir`` (now populated and marked complete).
    """
    if not force and is_complete(dest_dir):
        logger.info("dataco.skip_already_complete", dest_dir=str(dest_dir))
        return dest_dir

    parent = dest_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    partial_dir = parent / f"{dest_dir.name}.partial"

    # Wipe any partial from a previous interrupted run — we will redo the
    # whole download. We never resume mid-file because the Kaggle client
    # owns that contract; we resume at the source-level granularity.
    if partial_dir.exists():
        logger.info("dataco.cleaning_stale_partial", path=str(partial_dir))
        shutil.rmtree(partial_dir)
    partial_dir.mkdir()

    logger.info("dataco.download_start", dataset=dataset, path=str(partial_dir))
    client = client_factory()
    client.authenticate()
    client.dataset_download_files(dataset, path=str(partial_dir), unzip=True)
    logger.info("dataco.download_complete", path=str(partial_dir))

    # Atomic dir rename. Wipe any prior dest_dir first (e.g. a force-rerun).
    if dest_dir.exists():
        clear_complete_marker(dest_dir)
        shutil.rmtree(dest_dir)
    os.replace(partial_dir, dest_dir)

    mark_complete(dest_dir)
    logger.info("dataco.ready", dest_dir=str(dest_dir))
    return dest_dir


__all__ = ["DATACO_DATASET", "KaggleApiClient", "download_dataco"]
