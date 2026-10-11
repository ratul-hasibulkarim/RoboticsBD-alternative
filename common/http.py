"""Client wrapper for every outbound API call: timeouts, retries with jitter, circuit breaker.

The crawler's page fetcher (crawler/fetcher) builds on the same primitives but adds
robots.txt and per-host politeness; API clients (FX, Mouser, YouTube, ...) use
`ApiClient` directly.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from common.timeutil import utcnow

USER_AGENT = "VoltFindBot/1.0 (+https://voltfind.com/bot)"
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
MAX_BACKOFF_S = 3600.0


class CircuitOpenError(RuntimeError):
    """Raised when a host has failed too often recently; callers must back off."""


@dataclass
class CircuitBreaker:
    """Classic three-state breaker kept in process memory, keyed per host."""

    failure_threshold: int = 5
    reset_after_s: float = 60.0
    _failures: dict[str, int] = field(default_factory=dict)
    _opened_at: dict[str, float] = field(default_factory=dict)

    def before(self, host: str) -> None:
        opened = self._opened_at.get(host)
        if opened is None:
            return
        if time.monotonic() - opened < self.reset_after_s:
            raise CircuitOpenError(host)
        # half-open: allow one trial request
        del self._opened_at[host]
        self._failures[host] = self.failure_threshold - 1

    def success(self, host: str) -> None:
        self._failures.pop(host, None)
        self._opened_at.pop(host, None)

    def failure(self, host: str) -> None:
        n = self._failures.get(host, 0) + 1
        self._failures[host] = n
        if n >= self.failure_threshold:
            self._opened_at[host] = time.monotonic()

    def is_open(self, host: str) -> bool:
        return host in self._opened_at


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either delta-seconds or an HTTP-date (RFC 9110 §10.2.3)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), MAX_BACKOFF_S)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        return None
    return max(0.0, min((when - utcnow()).total_seconds(), MAX_BACKOFF_S))


def backoff_delay(attempt: int, base: float = 1.0, cap: float = MAX_BACKOFF_S) -> float:
    """Exponential backoff with full jitter (AWS architecture blog algorithm)."""
    return random.uniform(0, min(cap, base * (2**attempt)))


RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class ApiClient:
    """Thin async wrapper used by all API clients."""

    def __init__(
        self,
        base_url: str = "",
        *,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        breaker: CircuitBreaker | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            timeout=DEFAULT_TIMEOUT,
            http2=transport is None,
            transport=transport,
            follow_redirects=True,
        )
        self.max_retries = max_retries
        self.breaker = breaker or CircuitBreaker()
        self._sleep = sleep

    async def __aenter__(self) -> ApiClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = httpx.URL(url).host or httpx.URL(str(self._client.base_url)).host
        attempt = 0
        while True:
            self.breaker.before(host)
            try:
                resp = await self._client.request(method, url, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException):
                self.breaker.failure(host)
                if attempt >= self.max_retries:
                    raise
                await self._sleep(backoff_delay(attempt))
                attempt += 1
                continue
            if resp.status_code in RETRYABLE_STATUS:
                self.breaker.failure(host)
                if attempt >= self.max_retries:
                    return resp
                delay = parse_retry_after(resp.headers.get("Retry-After"))
                await self._sleep(delay if delay is not None else backoff_delay(attempt))
                attempt += 1
                continue
            self.breaker.success(host)
            return resp

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.request("GET", url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.request("POST", url, **kwargs)
        resp.raise_for_status()
        return resp.json()
