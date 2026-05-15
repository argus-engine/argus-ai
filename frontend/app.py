# SPDX-License-Identifier: Apache-2.0
"""Streamlit placeholder dashboard.

The single job this app does today is verify the docker-compose network end
to end: it calls the FastAPI service's ``/health`` route and shows the
response. That is enough to prove a clone-and-``docker-compose-up`` flow
works.

The full HITL reviewer surface — queue, structured disagreement capture,
active-learning feedback — replaces this in Phase 5.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

DEFAULT_API_URL = "http://api:8000"
API_URL = os.environ.get("ARGUS_API_URL", DEFAULT_API_URL)
REQUEST_TIMEOUT_S = 5.0


def _fetch_health(url: str) -> tuple[bool, dict[str, str] | str]:
    """Return ``(ok, payload_or_error)`` from a single GET to ``url/health``."""
    try:
        response = httpx.get(f"{url}/health", timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, str(exc)
    try:
        return True, response.json()
    except ValueError as exc:
        return False, f"invalid JSON from {url}/health: {exc}"


def main() -> None:
    st.set_page_config(
        page_title="Argus — placeholder dashboard",
        layout="wide",
    )

    st.title("Argus")
    st.caption("Multimodal, explainable, uncertainty-aware risk intelligence.")

    st.markdown(
        "This page is a **Phase 1 placeholder**. It exists so the local "
        "`docker-compose up` flow has a frontend container to verify the "
        "service network end to end. The full Human-in-the-Loop reviewer "
        "surface — queue, structured disagreement capture, active-learning "
        "feedback — replaces this in **Phase 5**."
    )

    st.divider()
    st.subheader("API connectivity")
    st.code(f"ARGUS_API_URL = {API_URL}", language="text")

    ok, payload = _fetch_health(API_URL)
    if ok:
        st.success("API is healthy.")
        st.json(payload)
    else:
        st.error(f"Could not reach API at {API_URL}/health")
        st.code(payload, language="text")


if __name__ == "__main__":  # pragma: no cover — Streamlit invokes the module
    main()
