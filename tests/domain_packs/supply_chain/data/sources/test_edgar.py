# SPDX-License-Identifier: Apache-2.0
"""Tests for the SEC EDGAR bounded-sample downloader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from argus.domain_packs.supply_chain.data.sources._http import (
    RateLimitedClient,
    TokenBucket,
)
from argus.domain_packs.supply_chain.data.sources._paths import is_complete
from argus.domain_packs.supply_chain.data.sources.edgar import (
    DEFAULT_USER_AGENT,
    USER_AGENT_ENV_VAR,
    document_url,
    download_edgar_sample,
    extract_recent_filings,
    resolve_user_agent,
    submissions_url,
)


@pytest.fixture()
def no_throttle_client() -> RateLimitedClient:
    class _NoSleepBucket(TokenBucket):
        def acquire(self) -> None:  # pragma: no cover
            return

    return RateLimitedClient(
        user_agent="Argus Platform test@example.com",
        rate_per_second=100,
        bucket=_NoSleepBucket(100),
    )


def _submissions_payload(
    *,
    forms: list[str],
    accessions: list[str] | None = None,
    primary_docs: list[str] | None = None,
) -> dict[str, object]:
    n = len(forms)
    accessions = accessions or [f"0000123-24-{i:06d}" for i in range(n)]
    primary_docs = primary_docs or [f"doc{i}.htm" for i in range(n)]
    return {
        "cik": "104169",
        "name": "TEST COMPANY",
        "filings": {
            "recent": {
                "form": forms,
                "accessionNumber": accessions,
                "filingDate": ["2024-01-15"] * n,
                "primaryDocument": primary_docs,
            }
        },
    }


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


class TestSubmissionsUrl:
    def test_format(self) -> None:
        assert (
            submissions_url("0000104169")
            == "https://data.sec.gov/submissions/CIK0000104169.json"
        )

    def test_rejects_non_ten_digit_cik(self) -> None:
        with pytest.raises(ValueError, match="10-digit"):
            submissions_url("104169")
        with pytest.raises(ValueError, match="10-digit"):
            submissions_url("00001041690")  # 11 digits

    def test_rejects_non_numeric_cik(self) -> None:
        with pytest.raises(ValueError, match="10-digit"):
            submissions_url("00000abcde")


class TestDocumentUrl:
    def test_drops_leading_zeros_from_cik(self) -> None:
        url = document_url("0000104169", "0000123-24-000001", "wmt.htm")
        assert url == "https://www.sec.gov/Archives/edgar/data/104169/000012324000001/wmt.htm"

    def test_strips_dashes_from_accession(self) -> None:
        url = document_url("0000018230", "9999999-24-123456", "cat.htm")
        assert "999999924123456" in url


# ---------------------------------------------------------------------------
# extract_recent_filings
# ---------------------------------------------------------------------------


class TestExtractRecentFilings:
    def test_picks_first_n_of_form(self) -> None:
        submissions = _submissions_payload(
            forms=["10-K", "10-Q", "8-K", "8-K", "8-K", "8-K", "10-K"],
        )
        eight_ks = extract_recent_filings(submissions, "8-K", 3)
        assert [f["accession"] for f in eight_ks] == [
            "0000123-24-000002",
            "0000123-24-000003",
            "0000123-24-000004",
        ]

    def test_returns_empty_when_form_absent(self) -> None:
        submissions = _submissions_payload(forms=["10-Q", "10-Q"])
        assert extract_recent_filings(submissions, "8-K", 5) == []

    def test_returns_fewer_than_limit_when_supply_short(self) -> None:
        submissions = _submissions_payload(forms=["10-K", "10-K"])
        assert len(extract_recent_filings(submissions, "10-K", 5)) == 2

    def test_handles_missing_filings_block(self) -> None:
        assert extract_recent_filings({}, "10-K", 3) == []
        assert extract_recent_filings({"filings": {}}, "10-K", 3) == []

    def test_payload_includes_required_fields(self) -> None:
        submissions = _submissions_payload(forms=["10-K"])
        [filing] = extract_recent_filings(submissions, "10-K", 1)
        assert set(filing.keys()) == {"accession", "filing_date", "primary_document"}


# ---------------------------------------------------------------------------
# resolve_user_agent
# ---------------------------------------------------------------------------


class TestResolveUserAgent:
    def test_explicit_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USER_AGENT_ENV_VAR, "Env Agent")
        assert resolve_user_agent("Explicit Agent") == "Explicit Agent"

    def test_env_var_used_when_no_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_AGENT_ENV_VAR, "Env Agent")
        assert resolve_user_agent() == "Env Agent"

    def test_default_used_when_no_env_or_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)
        assert resolve_user_agent() == DEFAULT_USER_AGENT


# ---------------------------------------------------------------------------
# download_edgar_sample
# ---------------------------------------------------------------------------


class TestDownloadEdgarSample:
    @pytest.fixture()
    def companies(self) -> dict[str, str]:
        return {"0000104169": "WMT", "0001048911": "FDX"}

    def _register_company(
        self,
        httpx_mock: HTTPXMock,
        *,
        cik: str,
        forms: list[str],
        accessions: list[str] | None = None,
        primary_docs: list[str] | None = None,
        doc_body: bytes = b"<html>filing</html>",
    ) -> None:
        payload = _submissions_payload(
            forms=forms, accessions=accessions, primary_docs=primary_docs
        )
        httpx_mock.add_response(
            url=submissions_url(cik),
            json=payload,
        )
        recent = payload["filings"]["recent"]  # type: ignore[index]
        for accession, primary in zip(
            recent["accessionNumber"],  # type: ignore[index]
            recent["primaryDocument"],  # type: ignore[index]
            strict=True,
        ):
            httpx_mock.add_response(
                url=document_url(cik, accession, primary),
                content=doc_body,
            )

    def test_full_run_writes_submissions_and_documents(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        companies: dict[str, str],
    ) -> None:
        for cik in companies:
            self._register_company(httpx_mock, cik=cik, forms=["10-K", "8-K", "8-K", "8-K"])

        dest = tmp_path / "edgar"
        download_edgar_sample(
            dest,
            companies=companies,
            http_client=no_throttle_client,
        )

        for cik, ticker in companies.items():
            company_dir = dest / f"{cik}_{ticker}"
            assert (company_dir / "submissions.json").exists()
            assert (company_dir / "10-K").exists()
            assert (company_dir / "8-K").exists()
            ten_ks = list((company_dir / "10-K").glob("*.html"))
            eight_ks = list((company_dir / "8-K").glob("*.html"))
            assert len(ten_ks) == 1
            assert len(eight_ks) == 3

    def test_marks_complete(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        companies: dict[str, str],
    ) -> None:
        for cik in companies:
            self._register_company(httpx_mock, cik=cik, forms=["10-K", "8-K", "8-K", "8-K"])
        dest = tmp_path / "edgar"
        download_edgar_sample(
            dest, companies=companies, http_client=no_throttle_client
        )
        assert is_complete(dest)

    def test_skip_when_already_complete(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
        companies: dict[str, str],
    ) -> None:
        dest = tmp_path / "edgar"
        dest.mkdir()
        (dest / ".complete").touch()
        download_edgar_sample(
            dest, companies=companies, http_client=no_throttle_client
        )
        # No requests made
        assert httpx_mock.get_requests() == []

    def test_cached_submissions_not_refetched(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
    ) -> None:
        cik = "0000104169"
        ticker = "WMT"
        dest = tmp_path / "edgar"
        company_dir = dest / f"{cik}_{ticker}"
        company_dir.mkdir(parents=True)

        # Pre-seed cached submissions JSON
        cached = _submissions_payload(forms=["10-K"], accessions=["AAA"], primary_docs=["a.htm"])
        (company_dir / "submissions.json").write_text(
            json.dumps(cached), encoding="utf-8"
        )

        # Only the document fetch is registered
        httpx_mock.add_response(
            url=document_url(cik, "AAA", "a.htm"),
            content=b"<html>x</html>",
        )

        download_edgar_sample(
            dest,
            companies={cik: ticker},
            forms=(("10-K", 1),),
            http_client=no_throttle_client,
        )
        # No submissions URL was hit because the cached file was used
        urls = [str(r.url) for r in httpx_mock.get_requests()]
        assert all("submissions" not in url for url in urls)

    def test_cached_document_not_refetched(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
    ) -> None:
        cik = "0000104169"
        ticker = "WMT"
        dest = tmp_path / "edgar"
        company_dir = dest / f"{cik}_{ticker}"
        ten_k_dir = company_dir / "10-K"
        ten_k_dir.mkdir(parents=True)

        # Cached submissions saying there's one 10-K filing
        cached = _submissions_payload(forms=["10-K"], accessions=["AAA"], primary_docs=["a.htm"])
        (company_dir / "submissions.json").write_text(
            json.dumps(cached), encoding="utf-8"
        )
        (ten_k_dir / "AAA.html").write_bytes(b"<html>cached</html>")

        # No URLs registered; if implementation tries to fetch, pytest_httpx fails the test
        download_edgar_sample(
            dest,
            companies={cik: ticker},
            forms=(("10-K", 1),),
            http_client=no_throttle_client,
        )
        assert httpx_mock.get_requests() == []
        assert (ten_k_dir / "AAA.html").read_bytes() == b"<html>cached</html>"

    def test_force_redownloads_after_complete(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
    ) -> None:
        cik = "0000104169"
        ticker = "WMT"
        dest = tmp_path / "edgar"
        dest.mkdir()
        (dest / ".complete").touch()

        # Force triggers the run; register URLs
        self._register_company(httpx_mock, cik=cik, forms=["10-K", "8-K", "8-K", "8-K"])
        download_edgar_sample(
            dest,
            companies={cik: ticker},
            http_client=no_throttle_client,
            force=True,
        )
        assert (dest / f"{cik}_{ticker}" / "submissions.json").exists()
        assert is_complete(dest)

    def test_form_without_matches_does_not_break_run(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
        no_throttle_client: RateLimitedClient,
    ) -> None:
        cik = "0000104169"
        ticker = "WMT"
        # Submissions JSON has only 10-Q filings; we ask for 10-K (missing).
        # Register *only* the submissions URL — no document URLs should be
        # hit because the form lookup returns an empty list.
        httpx_mock.add_response(
            url=submissions_url(cik),
            json=_submissions_payload(forms=["10-Q", "10-Q"]),
        )
        dest = tmp_path / "edgar"
        download_edgar_sample(
            dest,
            companies={cik: ticker},
            forms=(("10-K", 1),),
            http_client=no_throttle_client,
        )
        # Submissions JSON is downloaded; no documents (because no 10-K matches)
        company_dir = dest / f"{cik}_{ticker}"
        assert (company_dir / "submissions.json").exists()
        assert not (company_dir / "10-K").exists()
        # Run still marked complete
        assert is_complete(dest)
