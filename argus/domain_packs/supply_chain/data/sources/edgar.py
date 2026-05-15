# SPDX-License-Identifier: Apache-2.0
"""SEC EDGAR bounded-sample download.

The full EDGAR corpus hosts filings for tens of thousands of registrants;
we deliberately download a **fixed small sample** of supplier-relevant
US-listed companies. See ``docs/data_sources.md`` for the scope.

What we fetch per company:

- The ``submissions`` JSON index (a few hundred KB summarizing recent filings)
- The primary document of the **most recent 10-K**
- The primary documents of the **three most recent 8-Ks**

That is ≈ 4 documents per company × 6 companies = 24 documents total —
small, refreshable in seconds, and representative of the filings that
drive supply-chain disruption signals.

The SEC publishes a 10 req/s ceiling and requires every downloader to
identify themselves via the User-Agent header. We stay well under the
ceiling (8 req/s by default) and stamp every request with
"Argus Platform <email>". The User-Agent string is overridable via the
``ARGUS_EDGAR_USER_AGENT`` environment variable for users running with
their own identity.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

from argus.domain_packs.supply_chain.data.sources._http import RateLimitedClient
from argus.domain_packs.supply_chain.data.sources._paths import (
    atomic_write_bytes,
    clear_complete_marker,
    is_complete,
    mark_complete,
)

logger = structlog.get_logger(__name__)


EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

EDGAR_RATE_PER_SECOND = 8.0
"""Capped well below the SEC's published 10 req/s ceiling."""

DEFAULT_USER_AGENT = "Argus Platform soheiljafarifard@gmail.com"
"""Default User-Agent. Override via the ARGUS_EDGAR_USER_AGENT env var."""

USER_AGENT_ENV_VAR = "ARGUS_EDGAR_USER_AGENT"

DEFAULT_EDGAR_COMPANIES: dict[str, str] = {
    "0000104169": "WMT",   # Walmart — bellwether US retailer
    "0001048911": "FDX",   # FedEx — express logistics
    "0001090727": "UPS",   # UPS — ground + air logistics
    "0000909832": "COST",  # Costco — wholesale
    "0000027419": "TGT",   # Target — mid-market retail
    "0000018230": "CAT",   # Caterpillar — industrial supply chain
}
"""Fixed sample of supplier-relevant US-listed companies (CIK → ticker)."""

DEFAULT_FORMS: tuple[tuple[str, int], ...] = (("10-K", 1), ("8-K", 3))
"""For each company, fetch (form_type, max_count) pairs."""


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def submissions_url(cik: str) -> str:
    """Return the submissions JSON URL for a 10-digit zero-padded CIK."""
    if len(cik) != 10 or not cik.isdigit():
        raise ValueError(f"CIK must be a 10-digit zero-padded string, got {cik!r}")
    return f"{EDGAR_SUBMISSIONS_BASE}/CIK{cik}.json"


def document_url(cik: str, accession: str, primary_document: str) -> str:
    """Return the primary-document URL for a given filing.

    EDGAR file paths drop the leading zeros from the CIK and strip the
    dashes from the accession number; the on-disk path under
    ``Archives/edgar/data`` reflects that.
    """
    cik_int = int(cik)
    accession_no_dashes = accession.replace("-", "")
    return f"{EDGAR_ARCHIVES_BASE}/{cik_int}/{accession_no_dashes}/{primary_document}"


# ---------------------------------------------------------------------------
# Submissions JSON parsing
# ---------------------------------------------------------------------------


def extract_recent_filings(
    submissions: dict[str, Any],
    form: str,
    limit: int,
) -> list[dict[str, str]]:
    """Pull up to ``limit`` recent filings of ``form`` from a submissions JSON.

    The ``filings.recent`` block in the SEC submissions feed is a
    column-oriented structure (parallel arrays keyed by field name).
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_documents = recent.get("primaryDocument", [])

    matched: list[dict[str, str]] = []
    for index, candidate_form in enumerate(forms):
        if candidate_form != form:
            continue
        matched.append(
            {
                "accession": accession_numbers[index],
                "filing_date": filing_dates[index],
                "primary_document": primary_documents[index],
            }
        )
        if len(matched) >= limit:
            break
    return matched


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def resolve_user_agent(explicit: str | None = None) -> str:
    """Resolve the User-Agent: explicit arg → env var → default."""
    if explicit:
        return explicit
    return os.environ.get(USER_AGENT_ENV_VAR, DEFAULT_USER_AGENT)


def download_edgar_sample(
    dest_dir: Path,
    *,
    companies: dict[str, str] | None = None,
    forms: tuple[tuple[str, int], ...] = DEFAULT_FORMS,
    force: bool = False,
    user_agent: str | None = None,
    http_client: RateLimitedClient | None = None,
) -> Path:
    """Download the fixed-sample EDGAR filings into ``dest_dir``.

    Resumable: per-document files land under
    ``<dest>/<cik>_<ticker>/<form>/<accession>.html`` and are not
    re-downloaded if already present. The submissions JSON for each
    company is cached at ``<dest>/<cik>_<ticker>/submissions.json``.

    Idempotent: re-running on a fully-downloaded directory is a no-op
    via the ``.complete`` marker.

    Args:
        dest_dir: Final destination directory. Created if missing.
        companies: CIK → ticker mapping. Defaults to
            :data:`DEFAULT_EDGAR_COMPANIES`.
        forms: Iterable of (form_type, max_count) pairs. Defaults to one
            10-K and three 8-Ks per company.
        force: Re-run from scratch when ``True``.
        user_agent: Override the User-Agent header. Defaults to the
            ``ARGUS_EDGAR_USER_AGENT`` env var if set, otherwise
            :data:`DEFAULT_USER_AGENT`.
        http_client: Injected :class:`RateLimitedClient` (tests).
    """
    companies = companies or DEFAULT_EDGAR_COMPANIES

    if not force and is_complete(dest_dir):
        logger.info("edgar.skip_already_complete", dest_dir=str(dest_dir))
        return dest_dir

    dest_dir.mkdir(parents=True, exist_ok=True)
    if force:
        clear_complete_marker(dest_dir)

    owns_client = http_client is None
    client = http_client or RateLimitedClient(
        user_agent=resolve_user_agent(user_agent),
        rate_per_second=EDGAR_RATE_PER_SECOND,
    )

    try:
        for cik, ticker in companies.items():
            _download_company(client, dest_dir, cik=cik, ticker=ticker, forms=forms)
        mark_complete(dest_dir)
        logger.info("edgar.ready", dest_dir=str(dest_dir))
        return dest_dir
    finally:
        if owns_client:
            client.close()


def _download_company(
    client: RateLimitedClient,
    dest_dir: Path,
    *,
    cik: str,
    ticker: str,
    forms: tuple[tuple[str, int], ...],
) -> None:
    """Fetch submissions + the requested forms for one company."""
    company_dir = dest_dir / f"{cik}_{ticker}"
    company_dir.mkdir(exist_ok=True)

    submissions_path = company_dir / "submissions.json"
    if submissions_path.exists():
        logger.debug("edgar.submissions.cached", cik=cik, ticker=ticker)
        submissions: dict[str, Any] = json.loads(submissions_path.read_text(encoding="utf-8"))
    else:
        logger.info("edgar.submissions.fetch", cik=cik, ticker=ticker)
        response = client.get(submissions_url(cik))
        atomic_write_bytes(submissions_path, response.content)
        submissions = response.json()

    for form, limit in forms:
        filings = extract_recent_filings(submissions, form, limit)
        if not filings:
            logger.warning("edgar.form.empty", cik=cik, ticker=ticker, form=form)
            continue
        form_dir = company_dir / form
        form_dir.mkdir(exist_ok=True)
        for filing in filings:
            doc_path = form_dir / f"{filing['accession']}.html"
            if doc_path.exists():
                logger.debug(
                    "edgar.document.cached",
                    cik=cik,
                    ticker=ticker,
                    form=form,
                    accession=filing["accession"],
                )
                continue
            url = document_url(cik, filing["accession"], filing["primary_document"])
            logger.info(
                "edgar.document.fetch",
                cik=cik,
                ticker=ticker,
                form=form,
                accession=filing["accession"],
                url=url,
            )
            response = client.get(url)
            atomic_write_bytes(doc_path, response.content)


__all__ = [
    "DEFAULT_EDGAR_COMPANIES",
    "DEFAULT_FORMS",
    "DEFAULT_USER_AGENT",
    "EDGAR_ARCHIVES_BASE",
    "EDGAR_RATE_PER_SECOND",
    "EDGAR_SUBMISSIONS_BASE",
    "USER_AGENT_ENV_VAR",
    "document_url",
    "download_edgar_sample",
    "extract_recent_filings",
    "resolve_user_agent",
    "submissions_url",
]
