# SPDX-License-Identifier: Apache-2.0
"""Tests for the DataCo / Kaggle download wrapper.

The real ``kaggle`` package is never imported here — we substitute a
fake :class:`KaggleApiClient` Protocol implementation via the
``client_factory`` injection point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from argus.domain_packs.supply_chain.data.sources._paths import (
    is_complete,
    mark_complete,
)
from argus.domain_packs.supply_chain.data.sources.kaggle import (
    DATACO_DATASET,
    download_dataco,
)


@dataclass
class _FakeKaggleClient:
    """In-memory Kaggle client substitute.

    On ``dataset_download_files`` it writes a deterministic set of CSV files
    into the requested path, mimicking the unzip behavior of the real client.
    """

    authenticate_calls: int = 0
    download_calls: list[tuple[str, str]] = field(default_factory=list)
    files_to_write: dict[str, bytes] = field(
        default_factory=lambda: {
            "orders.csv": b"order_id,customer_id\nO-1,C-1\n",
            "suppliers.csv": b"supplier_id,name\nSUP-1,Acme\n",
        }
    )

    def authenticate(self) -> None:
        self.authenticate_calls += 1

    def dataset_download_files(
        self, dataset: str, *, path: str, unzip: bool = True
    ) -> None:
        self.download_calls.append((dataset, path))
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in self.files_to_write.items():
            (out / name).write_bytes(content)


class TestDownloadDataco:
    def test_default_dataset_slug_constant(self) -> None:
        # Public constant; downstream code may import it for logging.
        assert isinstance(DATACO_DATASET, str)
        assert "/" in DATACO_DATASET

    def test_writes_files_into_dest_dir(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient()
        result = download_dataco(dest, client_factory=lambda: fake)
        assert result == dest
        assert (dest / "orders.csv").read_bytes().startswith(b"order_id")
        assert (dest / "suppliers.csv").read_bytes().startswith(b"supplier_id")

    def test_marks_complete_after_download(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake)
        assert is_complete(dest) is True

    def test_skips_when_already_complete(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        mark_complete(dest)
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake)
        # No API calls because the .complete marker short-circuits
        assert fake.authenticate_calls == 0
        assert fake.download_calls == []

    def test_force_redownloads_even_when_complete(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        mark_complete(dest)
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake, force=True)
        assert fake.authenticate_calls == 1
        assert len(fake.download_calls) == 1
        # Marker re-set after the forced run
        assert is_complete(dest) is True

    def test_cleans_up_stale_partial_dir(self, tmp_path: Path) -> None:
        # Simulate an interrupted previous run.
        partial_dir = tmp_path / "dataco.partial"
        partial_dir.mkdir()
        (partial_dir / "leftover.txt").write_bytes(b"interrupted")

        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake)

        # The stale partial is gone and the real download landed cleanly.
        assert not partial_dir.exists()
        assert (dest / "orders.csv").exists()
        # Leftover from the interrupted run did NOT bleed into the final dest.
        assert not (dest / "leftover.txt").exists()

    def test_authenticates_before_download(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake)
        # Exactly one authentication for one download
        assert fake.authenticate_calls == 1

    def test_custom_dataset_slug_passed_through(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient()
        download_dataco(
            dest,
            dataset="alternative-user/alternative-slug",
            client_factory=lambda: fake,
        )
        assert fake.download_calls == [
            ("alternative-user/alternative-slug", str(tmp_path / "dataco.partial")),
        ]

    def test_partial_dir_removed_after_success(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake)
        assert not (tmp_path / "dataco.partial").exists()

    def test_atomic_rename_semantics(self, tmp_path: Path) -> None:
        # After a successful run, the final dest dir contains exactly the
        # files the Kaggle client wrote — no .partial naming leaked through.
        dest = tmp_path / "dataco"
        fake = _FakeKaggleClient(files_to_write={"a.csv": b"x", "b.csv": b"y"})
        download_dataco(dest, client_factory=lambda: fake)
        committed = sorted(p.name for p in dest.iterdir())
        assert committed == [".complete", "a.csv", "b.csv"]

    def test_force_path_clears_previous_complete_marker(self, tmp_path: Path) -> None:
        dest = tmp_path / "dataco"
        fake_a = _FakeKaggleClient(files_to_write={"old.csv": b"old"})
        download_dataco(dest, client_factory=lambda: fake_a)
        assert (dest / "old.csv").exists()

        fake_b = _FakeKaggleClient(files_to_write={"new.csv": b"new"})
        download_dataco(dest, client_factory=lambda: fake_b, force=True)
        # Forced re-run replaces the contents wholesale
        assert (dest / "new.csv").exists()
        assert not (dest / "old.csv").exists()


@pytest.mark.parametrize("force", [False, True])
class TestDownloadDatacoEnvironment:
    def test_creates_parent_directory_if_missing(
        self, tmp_path: Path, force: bool
    ) -> None:
        dest = tmp_path / "nested" / "deeper" / "dataco"
        fake = _FakeKaggleClient()
        download_dataco(dest, client_factory=lambda: fake, force=force)
        assert dest.exists()
        assert (dest / "orders.csv").exists()
