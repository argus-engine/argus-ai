# SPDX-License-Identifier: Apache-2.0
"""Rate-limited HTTP client shared by the GDELT and EDGAR source modules.

Both upstreams have explicit rate-limit policies:

- GDELT publishes the GKG at predictable 15-minute intervals; we deliberately
  stay well under any reasonable per-second rate.
- SEC EDGAR publishes a documented **10 requests/second** ceiling and asks
  every downloader to identify themselves via the User-Agent header.

Rather than duplicate throttle logic in two places, both modules share
:class:`RateLimitedClient`, which wraps ``httpx.Client`` with a token bucket
and stamps the User-Agent header on every request.

The token bucket is a simple "next allowed timestamp" implementation —
``time.monotonic`` for measurement, ``time.sleep`` for the wait. Tests
monkey-patch both to verify throttle behavior without real sleeps.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from types import TracebackType
from typing import Self

import httpx


class TokenBucket:
    """Minimal rate limiter: at most ``rate_per_second`` acquisitions per second.

    Implemented as a "next allowed timestamp": on each ``acquire()`` we sleep
    until at least ``1/rate`` seconds have elapsed since the previous call.
    Simple, monotonic, no background threads — fine for the modest fan-out
    of these source downloads.
    """

    __slots__ = ("_interval", "_next_allowed", "_now", "_sleep")

    def __init__(
        self,
        rate_per_second: float,
        *,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError(f"rate_per_second must be positive, got {rate_per_second}")
        self._interval = 1.0 / rate_per_second
        self._next_allowed = 0.0
        self._now = now
        self._sleep = sleep

    def acquire(self) -> None:
        """Block until the next acquisition is permitted."""
        now = self._now()
        wait = self._next_allowed - now
        if wait > 0:
            self._sleep(wait)
            now = self._now()
        self._next_allowed = now + self._interval


class RateLimitedClient:
    """``httpx.Client`` wrapper with token-bucket throttling and a fixed User-Agent.

    Designed for serial use (one logical caller at a time). Concurrent use
    from multiple threads is not supported — both SEC EDGAR and GDELT
    documentation discourage parallelizing requests, so single-threaded use
    is the right default.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        rate_per_second: float,
        timeout: float = 30.0,
        bucket: TokenBucket | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("user_agent must be a non-empty string")
        self._bucket = bucket or TokenBucket(rate_per_second)
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
        )
        self._user_agent = user_agent

    @property
    def user_agent(self) -> str:
        return self._user_agent

    def get(self, url: str, *, raise_for_status: bool = True) -> httpx.Response:
        """Throttled GET. Raises on non-2xx responses by default."""
        self._bucket.acquire()
        response = self._client.get(url)
        if raise_for_status:
            response.raise_for_status()
        return response

    def stream_get(self, url: str, *, chunk_size: int = 65_536) -> bytes:
        """Throttled GET that returns the full body. Suitable for ~10 MB payloads.

        Naming reflects intent — for streaming-to-disk callers should use
        ``stream_bytes`` and pipe to ``atomic_write_stream``.
        """
        return self.get(url).content

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["RateLimitedClient", "TokenBucket"]
