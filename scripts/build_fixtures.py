# SPDX-License-Identifier: Apache-2.0
"""Build deterministic small fixtures from downloaded raw data.

Reads from ``data/`` (populated by ``scripts/download_data.py``) and
writes seeded ~100-row samples to ``tests/fixtures/supply_chain/derived/``.
The hand-crafted edge-case fixtures already committed under
``tests/fixtures/supply_chain/`` remain the canonical test inputs;
the derived fixtures are real-data demonstrations and are picked up by
later-phase tests that exercise real-distribution data shapes.

Determinism: a fixed seed (``--seed``, default 42) drives
``random.Random.sample`` so the same input plus the same seed produces
byte-identical output. CI does not invoke this script.

Phase 1 scope: DataCo CSVs only. Conversion of GDELT GKG rows to the
``EventSignal`` shape and of EDGAR filings to ``Supplier``-shaped rows
lands in Phase 2 alongside the consumers that need them.
"""

from __future__ import annotations

import csv
import logging
import random
import sys
from pathlib import Path
from typing import Annotated

import structlog
import typer

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(stream=sys.stderr, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


logger = structlog.get_logger("argus.build_fixtures")


DATACO_FILES: tuple[str, ...] = (
    "DataCoSupplyChainDataset.csv",
    "orders.csv",
    "suppliers.csv",
    "shipments.csv",
)
"""Filenames we attempt to sample from data/dataco/.

DataCo's Kaggle bundle ships one large CSV by default
(DataCoSupplyChainDataset.csv); some forks split it into per-entity files.
We try the canonical name first, then per-entity fallbacks.
"""


def sample_csv(src: Path, dst: Path, *, n: int, seed: int) -> int:
    """Sample up to ``n`` rows from ``src`` into ``dst`` deterministically.

    Returns the number of rows written (which may be less than ``n`` if
    the source has fewer rows). The header is always preserved.
    """
    with src.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return 0
        rows = list(reader)

    rng = random.Random(seed)
    n_sample = min(n, len(rows))
    sampled = rng.sample(rows, n_sample) if n_sample > 0 else []

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(sampled)
    return n_sample


app = typer.Typer(
    help="Build deterministic small fixtures from downloaded raw data.",
    no_args_is_help=False,
    add_completion=False,
)


@app.command()
def main(
    source_dir: Annotated[
        Path,
        typer.Option("--source-dir", help="Root directory of downloaded data."),
    ] = Path("data"),
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Where to write the derived fixtures."),
    ] = Path("tests/fixtures/supply_chain/derived"),
    sample_size: Annotated[
        int,
        typer.Option("--sample-size", min=1, help="Max rows per fixture."),
    ] = 100,
    seed: Annotated[
        int,
        typer.Option("--seed", help="RNG seed for deterministic sampling."),
    ] = 42,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug-level logging."),
    ] = False,
) -> None:
    """Sample DataCo CSVs into ``output_dir`` and log what was processed."""
    _configure_logging(verbose)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataco_dir = source_dir / "dataco"
    processed = 0
    missing: list[str] = []

    for filename in DATACO_FILES:
        src = dataco_dir / filename
        if not src.exists():
            missing.append(filename)
            continue
        dst = output_dir / f"dataco_{filename}"
        rows = sample_csv(src, dst, n=sample_size, seed=seed)
        logger.info(
            "build_fixtures.sampled",
            source=str(src),
            destination=str(dst),
            rows=rows,
        )
        processed += 1

    if processed == 0:
        logger.warning(
            "build_fixtures.no_inputs",
            tried=list(DATACO_FILES),
            source_dir=str(dataco_dir),
            hint="run `python scripts/download_data.py --source kaggle` first",
        )
    else:
        logger.info(
            "build_fixtures.done",
            processed=processed,
            missing=missing,
        )


if __name__ == "__main__":  # pragma: no cover
    app()
