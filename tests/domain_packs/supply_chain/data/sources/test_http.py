# SPDX-License-Identifier: Apache-2.0
"""Tests for the rate-limited HTTP client and its token-bucket throttle.

Sleep and clock are injected so we can verify throttle behavior without
actually sleeping. Network is mocked via ``pytest_httpx``.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from argus.domain_packs.supply_chain.data.sources._http import (
    RateLimitedClient,
    TokenBucket,
)


class _FakeClock:
    """Monotonic clock substitute that advances only when ``sleep`` is called."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class TestTokenBucket:
    def test_rate_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            TokenBucket(0)
        with pytest.raises(ValueError, match="positive"):
            TokenBucket(-1)

    def test_first_acquire_is_free(self) -> None:
        clock = _FakeClock()
        bucket = TokenBucket(10, now=clock.time, sleep=clock.sleep)
        bucket.acquire()
        assert clock.sleeps == []

    def test_subsequent_acquires_throttle(self) -> None:
        clock = _FakeClock()
        bucket = TokenBucket(10, now=clock.time, sleep=clock.sleep)  # 100 ms interval
        bucket.acquire()
        bucket.acquire()
        bucket.acquire()
        # First call is free; second and third each sleep one interval (0.1 s)
        assert clock.sleeps == [pytest.approx(0.1), pytest.approx(0.1)]

    def test_no_sleep_when_caller_paces_itself(self) -> None:
        clock = _FakeClock()
        bucket = TokenBucket(10, now=clock.time, sleep=clock.sleep)
        bucket.acquire()
        clock.now += 0.5  # caller spent half a second before next request
        bucket.acquire()
        assert clock.sleeps == []  # no throttle needed

    def test_sleep_amount_matches_rate(self) -> None:
        clock = _FakeClock()
        bucket = TokenBucket(2, now=clock.time, sleep=clock.sleep)  # 0.5 s interval
        bucket.acquire()
        bucket.acquire()
        assert clock.sleeps == [pytest.approx(0.5)]


class TestRateLimitedClient:
    def test_user_agent_must_be_non_empty(self) -> None:
        with pytest.raises(ValueError, match="user_agent"):
            RateLimitedClient(user_agent="", rate_per_second=10)
        with pytest.raises(ValueError, match="user_agent"):
            RateLimitedClient(user_agent="   ", rate_per_second=10)

    def test_get_sends_user_agent_header(self, httpx_mock: HTTPXMock) -> None:
        ua = "Argus Platform test@example.com"
        httpx_mock.add_response(url="https://example.com/x", text="ok")
        with RateLimitedClient(user_agent=ua, rate_per_second=10) as client:
            response = client.get("https://example.com/x")
        assert response.text == "ok"
        sent = httpx_mock.get_requests()[0]
        assert sent.headers["User-Agent"] == ua

    def test_get_raises_for_non_2xx(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url="https://example.com/missing", status_code=404)
        with RateLimitedClient(user_agent="UA test@example.com", rate_per_second=10) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.get("https://example.com/missing")

    def test_get_can_return_non_2xx_when_asked(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url="https://example.com/missing", status_code=404)
        with RateLimitedClient(user_agent="UA test@example.com", rate_per_second=10) as client:
            response = client.get("https://example.com/missing", raise_for_status=False)
        assert response.status_code == 404

    def test_throttle_runs_before_each_request(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url="https://example.com/a", text="a")
        httpx_mock.add_response(url="https://example.com/b", text="b")
        httpx_mock.add_response(url="https://example.com/c", text="c")
        clock = _FakeClock()
        bucket = TokenBucket(10, now=clock.time, sleep=clock.sleep)
        with RateLimitedClient(
            user_agent="UA test@example.com",
            rate_per_second=10,
            bucket=bucket,
        ) as client:
            client.get("https://example.com/a")
            client.get("https://example.com/b")
            client.get("https://example.com/c")
        # First call free, two throttled
        assert clock.sleeps == [pytest.approx(0.1), pytest.approx(0.1)]

    def test_user_agent_property(self) -> None:
        ua = "Argus Platform soheiljafarifard@gmail.com"
        client = RateLimitedClient(user_agent=ua, rate_per_second=10)
        try:
            assert client.user_agent == ua
        finally:
            client.close()
