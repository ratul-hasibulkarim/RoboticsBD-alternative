"""The polite fetcher. Every page VoltFind ever downloads goes through `Fetcher.fetch`.

Order of checks for each URL (each hop of a redirect chain is checked again):
  1. legal gate (source approved + active)       → NotApprovedError
  2. source crawl_status == 'ok'                  → FetchStatus.SOURCE_PAUSED
  3. URL extension is not a binary we never fetch → FetchStatus.SKIPPED_TYPE
  4. robots.txt allows VoltFindBot (fail closed)  → FetchStatus.ROBOTS_DISALLOWED
  5. per-host rate limit (min of declared / Crawl-delay / Request-rate)
  6. conditional GET with stored ETag / Last-Modified
  7. response handling (304, 403/451, 429/503 Retry-After, 5xx backoff, size/type caps)
  8. wall detection (login / CAPTCHA / paywall)   → source flagged, page discarded
  9. raw body stored (30-day TTL) and crawl_pages row written
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from common.hashing import canonical_url, content_hash, url_hash
from common.http import backoff_delay, parse_retry_after
from common.timeutil import utcnow
from crawler.fetcher.ratelimit import HostRateLimiter, effective_interval_s
from crawler.fetcher.robots import RobotsCache
from crawler.fetcher.stores import PageRecord, PageStore, RawStore, SourceStateStore, raw_key
from crawler.fetcher.walls import detect_wall
from crawler.registry import SourceConfig

MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_RETRIES = 3
MAX_INLINE_WAIT_S = 30.0
MAX_REDIRECTS = 5

SKIP_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".zip",
        ".rar",
        ".7z",
        ".gz",
        ".tar",
        ".exe",
        ".dmg",
        ".iso",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".mp3",
        ".wav",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".avif",
        ".svg",
        ".step",
        ".stp",
        ".stl",
        ".brd",
        ".sch",
        ".gbr",
    }
)
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "application/json",
    "application/ld+json",
)


class FetchStatus(enum.StrEnum):
    OK = "ok"
    NOT_MODIFIED = "not_modified"
    UNCHANGED = "unchanged"  # 200 but identical content hash
    ROBOTS_DISALLOWED = "robots_disallowed"
    SOURCE_PAUSED = "source_paused"
    SOURCE_FLAGGED = "source_flagged"  # 403/451 or wall → source set to review_required
    SKIPPED_TYPE = "skipped_type"
    TOO_LARGE = "too_large"
    RETRY_LATER = "retry_later"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    OFF_SOURCE_REDIRECT = "off_source_redirect"


@dataclass(frozen=True)
class FetchResult:
    status: FetchStatus
    url: str
    final_url: str
    http_status: int | None = None
    body: bytes | None = None
    content_type: str | None = None
    content_hash: str | None = None
    raw_ref: str | None = None
    retry_after_s: float | None = None
    reason: str | None = None

    @property
    def needs_extraction(self) -> bool:
        return self.status is FetchStatus.OK


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _same_source(source: SourceConfig, url: str) -> bool:
    host = _host(url).removeprefix("www.")
    domain = source.domain.lower().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


class Fetcher:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        robots: RobotsCache,
        limiter: HostRateLimiter,
        pages: PageStore,
        source_state: SourceStateStore,
        raw: RawStore,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        import asyncio

        self.client = client
        self.robots = robots
        self.limiter = limiter
        self.pages = pages
        self.source_state = source_state
        self.raw = raw
        self._sleep = sleep or asyncio.sleep

    async def fetch(self, url: str, source: SourceConfig, source_id: uuid.UUID) -> FetchResult:
        source.require_approved()  # 1. legal gate — raises
        url = canonical_url(url)
        uhash = url_hash(url)

        if await self.source_state.crawl_status(source_id) != "ok":  # 2.
            return FetchResult(FetchStatus.SOURCE_PAUSED, url, url, reason="source crawl_status != ok")

        previous = await self.pages.previous(uhash)
        current = url
        attempt = 0
        redirects = 0

        while True:
            path = urlsplit(current).path.lower()
            if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):  # 3.
                return FetchResult(FetchStatus.SKIPPED_TYPE, url, current, reason="binary extension")
            if not _same_source(source, current):
                return FetchResult(FetchStatus.OFF_SOURCE_REDIRECT, url, current)

            rules = await self.robots.get(current)  # 4.
            if not rules.can_fetch(current):
                return FetchResult(FetchStatus.ROBOTS_DISALLOWED, url, current, reason=rules.state)

            host = _host(current)
            interval = effective_interval_s(source.rate_limit_rps, rules.crawl_delay(), rules.request_rate_rps())
            try:
                await self.limiter.acquire(host, interval)  # 5.
            except TimeoutError:
                return FetchResult(FetchStatus.RETRY_LATER, url, current, retry_after_s=interval)

            headers: dict[str, str] = {}
            if previous is not None and current == url:  # 6.
                if previous.etag:
                    headers["If-None-Match"] = previous.etag
                if previous.last_modified:
                    headers["If-Modified-Since"] = previous.last_modified

            try:
                async with self.client.stream("GET", current, headers=headers) as resp:
                    result = await self._handle(resp, url, current, source, source_id, uhash, previous)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt >= MAX_RETRIES:
                    await self._record_error(url, uhash, current, source_id, None, repr(exc))
                    return FetchResult(FetchStatus.NETWORK_ERROR, url, current, reason=repr(exc))
                await self._sleep(backoff_delay(attempt))
                attempt += 1
                continue

            if isinstance(result, _Redirect):
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    return FetchResult(FetchStatus.HTTP_ERROR, url, current, reason="too many redirects")
                current = canonical_url(result.location)
                continue
            if isinstance(result, _Retry):
                await self.limiter.penalize(host, result.delay)
                if attempt >= MAX_RETRIES or result.delay > MAX_INLINE_WAIT_S:
                    await self._record_error(url, uhash, current, source_id, result.status, "retry")
                    return FetchResult(
                        FetchStatus.RETRY_LATER,
                        url,
                        current,
                        http_status=result.status,
                        retry_after_s=result.delay,
                    )
                await self._sleep(result.delay)
                attempt += 1
                continue
            return result

    async def _handle(
        self,
        resp: httpx.Response,
        url: str,
        current: str,
        source: SourceConfig,
        source_id: uuid.UUID,
        uhash: str,
        previous: object,
    ) -> FetchResult | _Redirect | _Retry:
        status = resp.status_code

        if status in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location")
            if not loc:
                return FetchResult(FetchStatus.HTTP_ERROR, url, current, http_status=status)
            return _Redirect(str(resp.url.join(loc)))

        if status == 304:
            await self._record_meta(url, uhash, current, source_id, status)
            return FetchResult(FetchStatus.NOT_MODIFIED, url, current, http_status=304)

        if status in (403, 451):
            reason = f"HTTP {status} on {current}"
            await self.source_state.flag(source_id, "review_required", reason)
            await self._record_error(url, uhash, current, source_id, status, reason)
            return FetchResult(FetchStatus.SOURCE_FLAGGED, url, current, http_status=status, reason=reason)

        if status in (429, 503):
            delay = parse_retry_after(resp.headers.get("Retry-After"))
            return _Retry(status, delay if delay is not None else backoff_delay(0, base=2.0))

        if status >= 500:
            return _Retry(status, backoff_delay(1, base=2.0))

        if status >= 400:
            await self._record_error(url, uhash, current, source_id, status, f"HTTP {status}")
            return FetchResult(FetchStatus.HTTP_ERROR, url, current, http_status=status)

        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype and not ctype.startswith(ALLOWED_CONTENT_TYPES):
            return FetchResult(FetchStatus.SKIPPED_TYPE, url, current, http_status=status, content_type=ctype)

        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return FetchResult(FetchStatus.TOO_LARGE, url, current, http_status=status)

        chunks: list[bytes] = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                return FetchResult(FetchStatus.TOO_LARGE, url, current, http_status=status)
            chunks.append(chunk)
        body = b"".join(chunks)

        html = body.decode(resp.encoding or "utf-8", errors="replace")
        wall = detect_wall(html, status=status) if ctype.startswith(("text/html", "application/xhtml")) else None
        if wall is not None:
            reason = f"{wall} wall detected at {current}"
            await self.source_state.flag(source_id, "review_required", reason)
            await self._record_error(url, uhash, current, source_id, status, reason)
            return FetchResult(FetchStatus.SOURCE_FLAGGED, url, current, http_status=status, reason=reason)

        chash = content_hash(body)
        now = utcnow()
        prev_hash = getattr(previous, "content_hash", None)
        if prev_hash == chash:
            await self._record_meta(url, uhash, current, source_id, status)
            return FetchResult(FetchStatus.UNCHANGED, url, current, http_status=status, content_hash=chash)

        ref = await self.raw.put(raw_key(source.name, uhash, now), body, ctype or "text/html")
        await self.pages.record(
            PageRecord(
                url=url,
                url_hash=uhash,
                final_url=current,
                source_id=source_id,
                fetched_at=now,
                http_status=status,
                content_hash=chash,
                content_type=ctype or None,
                etag=resp.headers.get("etag"),
                last_modified=resp.headers.get("last-modified"),
                raw_ref=ref,
                error=None,
            )
        )
        return FetchResult(
            FetchStatus.OK,
            url,
            current,
            http_status=status,
            body=body,
            content_type=ctype or None,
            content_hash=chash,
            raw_ref=ref,
        )

    async def _record_meta(self, url: str, uhash: str, current: str, source_id: uuid.UUID, status: int) -> None:
        await self.pages.record(
            PageRecord(url, uhash, current, source_id, utcnow(), status, None, None, None, None, None, None)
        )

    async def _record_error(
        self,
        url: str,
        uhash: str,
        current: str,
        source_id: uuid.UUID,
        status: int | None,
        error: str,
    ) -> None:
        await self.pages.record(
            PageRecord(url, uhash, current, source_id, utcnow(), status, None, None, None, None, None, error)
        )


@dataclass(frozen=True)
class _Redirect:
    location: str


@dataclass(frozen=True)
class _Retry:
    status: int
    delay: float
