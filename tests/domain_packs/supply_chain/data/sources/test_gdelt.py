# SPDX-License-Identifier: Apache-2.0
"""Tests for the GDELT GKG bounded-subset download.

Network is fully mocked via pytest_httpx. Zip payloads are constructed
in-memory so the tests run hermetically.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from argus.domain_packs.supply_chain.data.sources._http import (
    RateLimitedClient,
    TokenBucket,
)
from argus.domain_packs.supply_chain.data.sources._paths import is_complete
from argus.domain_packs.supply_chain.data.sources.gdelt import (
    DEFAULT_GKG_THEMES,
    GDELT_BASE_URL,
    GKG_THEME_COLUMN_INDEX,
    download_gdelt_gkg_subset,
    filter_gkg_rows,
    iter_slots,
    slot_filename,
    slot_url,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers — build GKG-shaped CSV / zip payloads
# ---------------------------------------------------------------------------


def _gkg_row(
    record_id: str,
    *,
    themes: str = "OTHER_THEME",
    extras: str = "x" * 5,
) -> bytes:
    """Synthesize a single tab-separated row with themes at the right column."""
    fields = [extras] * 27
    fields[0] = record_id
    fields[GKG_THEME_COLUMN_INDEX] = themes
    return ("\t".join(fields) + "\n").encode("utf-8")


def _zip_with_csv(csv_payload: bytes, inner_name: str = "gkg.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, csv_payload)
    return buf.getvalue()


@pytest.fixture()
def no_throttle_client() -> RateLimitedClient:
    """Rate-limited client whose bucket never actually sleeps."""

    class _NoSleepBucket(TokenBucket):
        def acquire(self) -> None:  # pragma: no cover — deliberately empty
            return

    return RateLimitedClient(
        user_agent="Argus Platform test",
        rate_per_second=100,
        bucket=_NoSleepBucket(100),
    )


# ---------------------------------------------------------------------------
# iter_slots
# ---------------------------------------------------------------------------


class TestIterSlots:
    def test_aligned_window_inclusive_both_ends(self) -> None:
        start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 15, 1, 0, tzinfo=UTC)
        slots = list(iter_slots(start, end))
        # 00:00, 00:15, 00:30, 00:45, 01:00
        assert len(slots) == 5
        assert slots[0] == start
        assert slots[-1] == end

    def test_unaligned_start_rounds_up(self) -> None:
        start = datetime(2024, 1, 15, 12, 7, tzinfo=UTC)
        end = datetime(2024, 1, 15, 12, 50, tzinfo=UTC)
        slots = list(iter_slots(start, end))
        # 12:15, 12:30, 12:45 — 12:50 rounds down to 12:45
        assert [s.minute for s in slots] == [15, 30, 45]

    def test_one_slot_window(self) -> None:
        t = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        assert list(iter_slots(t, t)) == [t]

    def test_naive_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            list(iter_slots(datetime(2024, 1, 15), datetime(2024, 1, 15, tzinfo=UTC)))  # noqa: DTZ001

    def test_naive_end_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            list(iter_slots(datetime(2024, 1, 15, tzinfo=UTC), datetime(2024, 1, 15)))  # noqa: DTZ001

    def test_start_after_end_rejected(self) -> None:
        with pytest.raises(ValueError, match="after end"):
            list(
                iter_slots(
                    datetime(2024, 1, 16, tzinfo=UTC),
                    datetime(2024, 1, 15, tzinfo=UTC),
                )
            )


# ---------------------------------------------------------------------------
# URL / filename helpers
# ---------------------------------------------------------------------------


class TestSlotUrl:
    def test_url_format(self) -> None:
        slot = datetime(2024, 1, 15, 8, 30, tzinfo=UTC)
        assert slot_url(slot) == f"{GDELT_BASE_URL}/20240115083000.gkg.csv.zip"

    def test_non_utc_input_converted(self) -> None:
        tz = timezone(timedelta(hours=5))
        slot = datetime(2024, 1, 15, 13, 30, tzinfo=tz)  # 08:30 UTC
        assert slot_url(slot).endswith("20240115083000.gkg.csv.zip")

    def test_naive_slot_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            slot_url(datetime(2024, 1, 15))  # noqa: DTZ001


class TestSlotFilename:
    def test_filename_matches_url_basename(self) -> None:
        slot = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        assert slot_filename(slot) == "20240115000000.gkg.csv.zip"


# ---------------------------------------------------------------------------
# filter_gkg_rows
# ---------------------------------------------------------------------------


class TestFilterGkgRows:
    def test_keeps_rows_with_matching_theme(self) -> None:
        payload = (
            _gkg_row("a", themes="SUPPLY_CHAIN,123")
            + _gkg_row("b", themes="OTHER_THEME,1")
            + _gkg_row("c", themes="ECON_TRADE,500;NATURAL_DISASTER,2")
        )
        kept = list(filter_gkg_rows(payload, frozenset({"SUPPLY_CHAIN", "ECON_TRADE"})))
        assert len(kept) == 2
        assert b"\ta\t" in kept[0] or kept[0].startswith(b"a\t")
        assert b"\tc\t" in kept[1] or kept[1].startswith(b"c\t")

    def test_drops_rows_without_any_match(self) -> None:
        payload = _gkg_row("a", themes="UNRELATED_THEME")
        assert list(filter_gkg_rows(payload, frozenset({"SUPPLY_CHAIN"}))) == []

    def test_empty_themes_yields_nothing(self) -> None:
        payload = _gkg_row("a", themes="SUPPLY_CHAIN,1")
        assert list(filter_gkg_rows(payload, frozenset())) == []

    def test_handles_short_rows(self) -> None:
        # A degenerate row with fewer than 8 columns is skipped, not raised
        short_row = b"only\ttwo\tcols\n"
        assert list(filter_gkg_rows(short_row, frozenset({"SUPPLY_CHAIN"}))) == []

    def test_handles_empty_input(self) -> None:
        assert list(filter_gkg_rows(b"", DEFAULT_GKG_THEMES)) == []


# ---------------------------------------------------------------------------
# download_gdelt_gkg_subset
# ---------------------------------------------------------------------------


class TestDownloadGdeltGkgSubset:
    @pytest.fixture()
    def window(self) -> tuple[datetime, datetime]:
        start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 15, 0, 15, tzinfo=UTC)
        return start, end

    def _register_slots(
        self,
        httpx_mock: HTTPXMock,
        slots_payload: dict[datetime, bytes],
    ) -> None:
        for slot, csv_payload in slots_payload.items():
            httpx_mock.add_response(
                url=slot_url(slot),
                content=_zip_with_csv(csv_payload),
            )

    def test_downloads_slots_and_writes_filtered_output(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        slots = list(iter_slots(start, end))
        # Slot 0: matches; Slot 1: doesn't
        payloads = {
            slots[0]: _gkg_row("kept", themes="SUPPLY_CHAIN,1"),
            slots[1]: _gkg_row("dropped", themes="UNRELATED,1"),
        }
        self._register_slots(httpx_mock, payloads)

        dest = tmp_path / "gdelt"
        output = download_gdelt_gkg_subset(
            dest,
            start=start,
            end=end,
            http_client=no_throttle_client,
        )
        assert output.exists()
        text = output.read_text(encoding="utf-8")
        assert "kept" in text
        assert "dropped" not in text

    def test_marks_complete(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        slots = list(iter_slots(start, end))
        self._register_slots(httpx_mock, {s: _gkg_row("x", themes="SUPPLY_CHAIN,1") for s in slots})
        dest = tmp_path / "gdelt"
        download_gdelt_gkg_subset(
            dest, start=start, end=end, http_client=no_throttle_client
        )
        assert is_complete(dest)

    def test_skips_when_complete(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        dest = tmp_path / "gdelt"
        dest.mkdir()
        (dest / ".complete").touch()
        # No httpx_mock responses registered — if the implementation tried
        # to fetch, pytest_httpx would complain about unregistered URLs.
        download_gdelt_gkg_subset(
            dest, start=start, end=end, http_client=no_throttle_client
        )
        assert httpx_mock.get_requests() == []

    def test_resumable_skips_cached_slots(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        slots = list(iter_slots(start, end))
        dest = tmp_path / "gdelt"
        raw_dir = dest / "raw"
        raw_dir.mkdir(parents=True)

        # Pre-seed the first slot's cached file
        (raw_dir / slot_filename(slots[0])).write_bytes(
            _zip_with_csv(_gkg_row("cached_kept", themes="SUPPLY_CHAIN,1"))
        )
        # Only the second slot needs to be fetched
        httpx_mock.add_response(
            url=slot_url(slots[1]),
            content=_zip_with_csv(_gkg_row("freshly_kept", themes="ECON_TRADE,1")),
        )

        download_gdelt_gkg_subset(
            dest, start=start, end=end, http_client=no_throttle_client
        )
        text = (dest / "gkg_20240115_to_20240115.csv").read_text(encoding="utf-8")
        assert "cached_kept" in text
        assert "freshly_kept" in text

    def test_empty_themes_rejected(
        self,
        tmp_path: Path,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        with pytest.raises(ValueError, match="non-empty"):
            download_gdelt_gkg_subset(
                tmp_path / "gdelt",
                start=start,
                end=end,
                themes=set(),
                http_client=no_throttle_client,
            )

    def test_custom_themes_filter_correctly(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        slots = list(iter_slots(start, end))
        payloads = {
            slots[0]: _gkg_row("matches_custom", themes="CYBER_ATTACK,5"),
            slots[1]: _gkg_row("does_not", themes="SUPPLY_CHAIN,5"),
        }
        self._register_slots(httpx_mock, payloads)
        dest = tmp_path / "gdelt"
        output = download_gdelt_gkg_subset(
            dest,
            start=start,
            end=end,
            themes={"CYBER_ATTACK"},
            http_client=no_throttle_client,
        )
        text = output.read_text(encoding="utf-8")
        assert "matches_custom" in text
        assert "does_not" not in text

    def test_output_path_includes_window_dates(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        window: tuple[datetime, datetime],
    ) -> None:
        start, end = window
        slots = list(iter_slots(start, end))
        for s in slots:
            httpx_mock.add_response(
                url=slot_url(s),
                content=_zip_with_csv(_gkg_row("x", themes="SUPPLY_CHAIN,1")),
            )
        output = download_gdelt_gkg_subset(
            tmp_path / "gdelt",
            start=start,
            end=end,
            http_client=no_throttle_client,
        )
        assert output.name == "gkg_20240115_to_20240115.csv"
