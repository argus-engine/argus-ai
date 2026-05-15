# SPDX-License-Identifier: Apache-2.0
"""CLI front-end for downloading the supply-chain reference datasets.

This script is a thin shim over the functions in
``argus.domain_packs.supply_chain.data.sources``. The real download logic
lives there so it can be unit-tested without invoking the CLI; this file
just parses arguments, configures structured logging, and dispatches.

Examples::

    python scripts/download_data.py                       # default: all sources
    python scripts/download_data.py --source kaggle
    python scripts/download_data.py --source gdelt \\
        --gdelt-start 2024-01-15 --gdelt-end 2024-01-22
    python scripts/download_data.py --source edgar --force
    python scripts/download_data.py --source all --dry-run

The script never touches the network in ``--dry-run`` mode; it only logs
the plan. See ``docs/data_sources.md`` for the scope of each source.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated

import structlog
import typer

# Make the script runnable both as `python scripts/download_data.py` (where
# the script's directory, not the repo root, is on sys.path) and as a
# module. Prepending the repo root to sys.path is a small ergonomic
# concession to the brief's "scripts/download_data.py" invocation.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argus.domain_packs.supply_chain.data.sources import (  # noqa: E402
    DEFAULT_GKG_THEMES,
    download_dataco,
    download_edgar_sample,
    download_gdelt_gkg_subset,
)


class Source(str, Enum):
    """Which upstream to fetch."""

    KAGGLE = "kaggle"
    GDELT = "gdelt"
    EDGAR = "edgar"
    ALL = "all"


def _configure_logging(verbose: bool) -> None:
    """Set up structlog to emit human-readable lines to stderr."""
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


logger = structlog.get_logger("argus.download_data")


app = typer.Typer(
    help="Download supply-chain reference datasets (DataCo, GDELT, SEC EDGAR).",
    no_args_is_help=False,
    add_completion=False,
)


@app.command()
def main(
    source: Annotated[
        Source,
        typer.Option(
            "--source",
            "-s",
            help="Which source(s) to download.",
            case_sensitive=False,
        ),
    ] = Source.ALL,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Root directory for downloaded data (gitignored).",
        ),
    ] = Path("data"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Ignore .complete markers and re-download."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Log the plan but do not actually fetch anything.",
        ),
    ] = False,
    gdelt_start: Annotated[
        datetime,
        typer.Option(
            "--gdelt-start",
            help="GDELT subset window start (UTC). ISO 8601.",
        ),
    ] = datetime(2024, 1, 15, tzinfo=timezone.utc),
    gdelt_end: Annotated[
        datetime,
        typer.Option(
            "--gdelt-end",
            help="GDELT subset window end (UTC). ISO 8601.",
        ),
    ] = datetime(2024, 1, 22, tzinfo=timezone.utc),
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug-level logging."),
    ] = False,
) -> None:
    """Download supply-chain reference datasets per the scope in ``docs/data_sources.md``."""
    _configure_logging(verbose)

    # Typer parses --gdelt-start/--gdelt-end as datetimes but they may come
    # in naive on certain platforms; coerce to UTC for safety.
    if gdelt_start.tzinfo is None:
        gdelt_start = gdelt_start.replace(tzinfo=timezone.utc)
    if gdelt_end.tzinfo is None:
        gdelt_end = gdelt_end.replace(tzinfo=timezone.utc)

    sources = _expand_source_selection(source)
    logger.info(
        "download_data.plan",
        sources=[s.value for s in sources],
        output_dir=str(output_dir),
        force=force,
        dry_run=dry_run,
    )

    if dry_run:
        for s in sources:
            logger.info("download_data.dry_run.would_run", source=s.value)
        raise typer.Exit(code=0)

    output_dir.mkdir(parents=True, exist_ok=True)

    if Source.KAGGLE in sources:
        download_dataco(output_dir / "dataco", force=force)
    if Source.GDELT in sources:
        download_gdelt_gkg_subset(
            output_dir / "gdelt",
            start=gdelt_start,
            end=gdelt_end,
            themes=DEFAULT_GKG_THEMES,
            force=force,
        )
    if Source.EDGAR in sources:
        download_edgar_sample(output_dir / "edgar", force=force)

    logger.info("download_data.done")


def _expand_source_selection(source: Source) -> list[Source]:
    if source is Source.ALL:
        return [Source.KAGGLE, Source.GDELT, Source.EDGAR]
    return [source]


if __name__ == "__main__":  # pragma: no cover
    app()
