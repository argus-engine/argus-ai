# SPDX-License-Identifier: Apache-2.0
"""GDELT 2.0 GKG bounded-subset download.

GDELT publishes a new Global Knowledge Graph (GKG) file every 15 minutes
under ``http://data.gdeltproject.org/gdeltv2/<YYYYMMDDHHMMSS>.gkg.csv.zip``.
The **full** historical corpus is in the terabyte range — we deliberately
do not download it. See ``docs/data_sources.md`` for the subset definition.

This module:

1. Enumerates 15-minute slot timestamps between a configurable
   ``[start, end]`` window (default one week)
2. Downloads each slot's zip via the shared :class:`RateLimitedClient`
3. Filters rows whose ``V1Themes`` cell intersects a configurable set of
   supply-chain-relevant themes (default: ``SUPPLY_CHAIN``,
   ``INFRASTRUCTURE_BAD_CONDITIONS``, ``NATURAL_DISASTER``, ``ECON_TRADE``)
4. Concatenates the filtered rows into a single CSV at
   ``<dest_dir>/gkg_<start>_to_<end>.csv``

Per-slot files are cached under ``<dest_dir>/raw/`` so an interrupted run
resumes on the next invocation. The ``.complete`` marker is only touched
after every slot is present and the filtered output has been written.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

from argus.domain_packs.supply_chain.data.sources._http import RateLimitedClient
from argus.domain_packs.supply_chain.data.sources._paths import (
    atomic_write_bytes,
    clear_complete_marker,
    is_complete,
    mark_complete,
)

logger = structlog.get_logger(__name__)


GDELT_BASE_URL = "http://data.gdeltproject.org/gdeltv2"
"""GDELT 2.0 public file root."""

GKG_THEME_COLUMN_INDEX = 7
"""Column index (0-based) of ``V1Themes`` in the GKG 2.0 tab-separated layout."""

DEFAULT_GKG_THEMES = frozenset(
    {
        "SUPPLY_CHAIN",
        "INFRASTRUCTURE_BAD_CONDITIONS",
        "NATURAL_DISASTER",
        "ECON_TRADE",
    }
)
"""The four GKG themes we filter to by default — see docs/data_sources.md."""

DEFAULT_USER_AGENT = "Argus Platform soheiljafarifard@gmail.com"
"""User-Agent used when no explicit client is passed. The string identifies
the project and a contact email so upstream operators can reach us if our
downloads cause concern."""

GDELT_RATE_PER_SECOND = 2.0
"""Polite default for GDELT — they publish no hard limit but ask that
downloaders avoid hammering the static file host."""


# ---------------------------------------------------------------------------
# Slot enumeration
# ---------------------------------------------------------------------------


def _floor_to_quarter_hour(t: datetime) -> datetime:
    """Round ``t`` down to the nearest 15-minute boundary."""
    return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)


def _ceil_to_quarter_hour(t: datetime) -> datetime:
    """Round ``t`` up to the nearest 15-minute boundary."""
    floored = _floor_to_quarter_hour(t)
    return floored if floored == t else floored + timedelta(minutes=15)


def iter_slots(start: datetime, end: datetime) -> Iterator[datetime]:
    """Yield 15-minute-aligned UTC slot timestamps in ``[start, end]``.

    Both endpoints must be timezone-aware. ``start`` is rounded **up** to
    the next 15-minute boundary; ``end`` is rounded **down**. This means
    requesting ``[12:07, 12:50]`` yields ``12:15``, ``12:30``, ``12:45``.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start > end:
        raise ValueError(f"start ({start}) is after end ({end})")
    current = _ceil_to_quarter_hour(start.astimezone(timezone.utc))
    last = _floor_to_quarter_hour(end.astimezone(timezone.utc))
    while current <= last:
        yield current
        current += timedelta(minutes=15)


def slot_url(slot: datetime) -> str:
    """Return the GDELT 2.0 GKG zip URL for a 15-minute slot."""
    if slot.tzinfo is None:
        raise ValueError("slot must be timezone-aware")
    stamp = slot.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{GDELT_BASE_URL}/{stamp}.gkg.csv.zip"


def slot_filename(slot: datetime) -> str:
    """Filename used for the per-slot cache."""
    stamp = slot.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{stamp}.gkg.csv.zip"


# ---------------------------------------------------------------------------
# Theme filtering
# ---------------------------------------------------------------------------


def filter_gkg_rows(
    csv_bytes: bytes,
    themes: frozenset[str],
) -> Iterator[bytes]:
    """Yield raw CSV rows from a GKG file whose Themes cell intersects ``themes``.

    The GKG file is tab-separated (despite the .csv extension); each row's
    ``V1Themes`` cell is semicolon-delimited "THEME,offset" pairs. We do a
    simple substring scan — robust to minor format drift and fast enough for
    multi-MB rows.
    """
    if not themes:
        return
    for raw_line in csv_bytes.splitlines(keepends=True):
        try:
            line = raw_line.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        parts = line.split("\t")
        if len(parts) <= GKG_THEME_COLUMN_INDEX:
            continue
        theme_cell = parts[GKG_THEME_COLUMN_INDEX]
        if any(theme in theme_cell for theme in themes):
            yield raw_line


def _extract_csv_from_zip(zip_bytes: bytes) -> bytes:
    """Return the single CSV payload from a GDELT GKG zip.

    Empty zips and zips with no entries are tolerated — they yield ``b""``,
    so an empty slot does not abort the whole run.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        if not names:
            return b""
        with zf.open(names[0]) as fh:
            return fh.read()


# ---------------------------------------------------------------------------
# Public download entrypoint
# ---------------------------------------------------------------------------


def download_gdelt_gkg_subset(
    dest_dir: Path,
    *,
    start: datetime,
    end: datetime,
    themes: Iterable[str] = DEFAULT_GKG_THEMES,
    force: bool = False,
    http_client: RateLimitedClient | None = None,
) -> Path:
    """Download GDELT GKG slots, filter to ``themes``, and write one CSV.

    Idempotent at the source granularity (skips when ``.complete`` is set)
    and at the slot granularity (per-slot zips are cached under ``raw/``
    and not re-downloaded on resumed runs).

    Args:
        dest_dir: Output directory. Created if missing.
        start: Lower bound, timezone-aware. Rounded up to a 15-min boundary.
        end: Upper bound, timezone-aware. Rounded down to a 15-min boundary.
        themes: Set of theme strings to retain. Defaults to
            :data:`DEFAULT_GKG_THEMES`.
        force: Re-run from scratch when ``True`` — wipes ``.complete`` and
            re-filters. Per-slot raw files are kept across forces because
            they're the expensive part.
        http_client: Optional injected :class:`RateLimitedClient` (tests).
            Defaults to a fresh client honoring :data:`GDELT_RATE_PER_SECOND`.

    Returns:
        Path to the concatenated filtered CSV.
    """
    theme_set = frozenset(themes)
    if not theme_set:
        raise ValueError("themes must be a non-empty set")

    if not force and is_complete(dest_dir):
        logger.info("gdelt.skip_already_complete", dest_dir=str(dest_dir))
        return _output_path(dest_dir, start, end)

    dest_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = dest_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    if force:
        clear_complete_marker(dest_dir)

    owns_client = http_client is None
    client = http_client or RateLimitedClient(
        user_agent=DEFAULT_USER_AGENT,
        rate_per_second=GDELT_RATE_PER_SECOND,
    )

    try:
        slots = list(iter_slots(start, end))
        logger.info("gdelt.plan", n_slots=len(slots), themes=sorted(theme_set))

        for slot in slots:
            slot_path = raw_dir / slot_filename(slot)
            if slot_path.exists():
                logger.debug("gdelt.slot.cached", slot=slot.isoformat())
                continue
            url = slot_url(slot)
            logger.info("gdelt.slot.download", slot=slot.isoformat(), url=url)
            content = client.get(url).content
            atomic_write_bytes(slot_path, content)

        output_path = _output_path(dest_dir, start, end)
        _write_filtered_output(raw_dir, output_path, slots, theme_set)
        logger.info(
            "gdelt.filtered_output_written",
            output=str(output_path),
            themes=sorted(theme_set),
        )

        mark_complete(dest_dir)
        return output_path
    finally:
        if owns_client:
            client.close()


def _output_path(dest_dir: Path, start: datetime, end: datetime) -> Path:
    start_s = start.astimezone(timezone.utc).strftime("%Y%m%d")
    end_s = end.astimezone(timezone.utc).strftime("%Y%m%d")
    return dest_dir / f"gkg_{start_s}_to_{end_s}.csv"


def _write_filtered_output(
    raw_dir: Path,
    output_path: Path,
    slots: list[datetime],
    themes: frozenset[str],
) -> None:
    """Combine per-slot filtered rows into ``output_path`` atomically."""
    parts: list[bytes] = []
    for slot in slots:
        slot_path = raw_dir / slot_filename(slot)
        if not slot_path.exists():
            continue
        csv_bytes = _extract_csv_from_zip(slot_path.read_bytes())
        parts.extend(filter_gkg_rows(csv_bytes, themes))
    atomic_write_bytes(output_path, b"".join(parts))


__all__ = [
    "DEFAULT_GKG_THEMES",
    "DEFAULT_USER_AGENT",
    "GDELT_BASE_URL",
    "GDELT_RATE_PER_SECOND",
    "GKG_THEME_COLUMN_INDEX",
    "download_gdelt_gkg_subset",
    "filter_gkg_rows",
    "iter_slots",
    "slot_filename",
    "slot_url",
]
