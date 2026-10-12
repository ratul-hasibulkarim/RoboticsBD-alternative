"""C3, C4 and the fetcher's politeness rules."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
import respx

from common.http import USER_AGENT
from crawler.fetcher.client import build_crawler_client
from crawler.fetcher.ratelimit import HostRateLimiter
from crawler.fetcher.robots import RobotsCache
from crawler.fetcher.worker import MAX_BODY_BYTES, Fetcher, FetchStatus
from crawler.registry import NotApprovedError
from crawler.tests.conftest import MemoryPageStore, MemoryRawStore, MemorySourceState, make_source

PRODUCT_HTML = b"""<html><head><title>ESP32-WROOM-32 | Test Shop</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"ESP32-WROOM-32"}</script>
</head><body><h1>ESP32-WROOM-32</h1></body></html>"""


@dataclass
class Rig:
    fetcher: Fetcher
    pages: MemoryPageStore
    state: MemorySourceState
    raw: MemoryRawStore
    sleeps: list[float]
    source_id: uuid.UUID


@pytest.fixture
async def rig(redis) -> AsyncIterator[Rig]:  # type: ignore[no-untyped-def]
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    client = build_crawler_client()
    pages, state, raw = MemoryPageStore(), MemorySourceState(), MemoryRawStore()
    fetcher = Fetcher(
        client=client,
        robots=RobotsCache(redis, client),
        limiter=HostRateLimiter(redis),
        pages=pages,
        source_state=state,
        raw=raw,
        sleep=fake_sleep,
    )
    yield Rig(fetcher, pages, state, raw, sleeps, uuid.uuid4())
    await client.aclose()


def _robots(text: str = "User-agent: *\nAllow: /\n") -> None:
    respx.get("https://shop.test/robots.txt").respond(200, text=text)


@respx.mock
async def test_ok_fetch_stores_raw_and_page(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/p/esp32").respond(
        200, content=PRODUCT_HTML, headers={"content-type": "text/html; charset=utf-8", "etag": '"v1"'}
    )
    res = await rig.fetcher.fetch("https://shop.test/p/esp32", make_source(), rig.source_id)
    assert res.status is FetchStatus.OK
    assert res.body == PRODUCT_HTML
    assert res.raw_ref in rig.raw.objects
    assert next(iter(rig.pages.rows.values())).etag == '"v1"'


@respx.mock
async def test_user_agent_is_constant(rig: Rig) -> None:
    _robots()
    route = respx.get("https://shop.test/p/1").respond(200, content=PRODUCT_HTML, headers={"content-type": "text/html"})
    await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert route.calls.last.request.headers["user-agent"] == USER_AGENT
    assert "cookie" not in route.calls.last.request.headers


@respx.mock
async def test_no_cookies_are_replayed(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/p/1").respond(
        200, content=PRODUCT_HTML, headers={"content-type": "text/html", "set-cookie": "sid=abc; Path=/"}
    )
    route2 = respx.get("https://shop.test/p/2").respond(
        200, content=PRODUCT_HTML + b" ", headers={"content-type": "text/html"}
    )
    await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    await rig.fetcher.fetch("https://shop.test/p/2", make_source(), rig.source_id)
    assert "cookie" not in route2.calls.last.request.headers


@respx.mock
async def test_unapproved_source_raises(rig: Rig) -> None:
    src = make_source(legal_review={"status": "pending"})
    with pytest.raises(NotApprovedError):
        await rig.fetcher.fetch("https://shop.test/p/1", src, rig.source_id)
    inactive = make_source(active=False)
    with pytest.raises(NotApprovedError):
        await rig.fetcher.fetch("https://shop.test/p/1", inactive, rig.source_id)


@respx.mock
async def test_robots_disallow_blocks_fetch(rig: Rig) -> None:
    _robots("User-agent: VoltFindBot\nDisallow: /p/\n")
    route = respx.get("https://shop.test/p/1").respond(200)
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.ROBOTS_DISALLOWED
    assert route.call_count == 0


@respx.mock
async def test_robots_unreachable_blocks_fetch(rig: Rig) -> None:
    respx.get("https://shop.test/robots.txt").mock(side_effect=httpx.ConnectTimeout("t"))
    route = respx.get("https://shop.test/p/1").respond(200)
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.ROBOTS_DISALLOWED
    assert route.call_count == 0


@respx.mock
@pytest.mark.parametrize("code", [403, 451])
async def test_403_flips_source(rig: Rig, code: int) -> None:
    """C3: source flips to review_required in < 1 s and further fetches stop."""
    _robots()
    respx.get("https://shop.test/p/1").respond(code)
    route2 = respx.get("https://shop.test/p/2").respond(200)
    t0 = time.monotonic()
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    elapsed = time.monotonic() - t0
    assert res.status is FetchStatus.SOURCE_FLAGGED
    assert rig.state.status[rig.source_id] == "review_required"
    assert elapsed < 1.0
    res2 = await rig.fetcher.fetch("https://shop.test/p/2", make_source(), rig.source_id)
    assert res2.status is FetchStatus.SOURCE_PAUSED
    assert route2.call_count == 0


@respx.mock
async def test_conditional_get_second_fetch_is_304(rig: Rig) -> None:
    """C4: unchanged page → 304, no re-extract."""
    _robots()
    route = respx.get("https://shop.test/p/1")
    route.side_effect = [
        httpx.Response(
            200,
            content=PRODUCT_HTML,
            headers={"content-type": "text/html", "etag": '"abc"', "last-modified": "Wed, 01 Oct 2026 10:00:00 GMT"},
        ),
        httpx.Response(304),
    ]
    first = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    second = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert first.needs_extraction
    assert second.status is FetchStatus.NOT_MODIFIED
    assert not second.needs_extraction
    req = route.calls.last.request
    assert req.headers["if-none-match"] == '"abc"'
    assert req.headers["if-modified-since"] == "Wed, 01 Oct 2026 10:00:00 GMT"
    assert len(rig.raw.objects) == 1


@respx.mock
async def test_identical_content_without_validators_is_unchanged(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/p/1").respond(200, content=PRODUCT_HTML, headers={"content-type": "text/html"})
    await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    again = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert again.status is FetchStatus.UNCHANGED
    assert not again.needs_extraction


@respx.mock
async def test_retry_after_seconds_respected(rig: Rig) -> None:
    _robots()
    route = respx.get("https://shop.test/p/1")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, content=PRODUCT_HTML, headers={"content-type": "text/html"}),
    ]
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.OK
    assert 7.0 in rig.sleeps


@respx.mock
async def test_retry_after_long_defers_to_scheduler(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/p/1").respond(503, headers={"Retry-After": "600"})
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.RETRY_LATER
    assert res.retry_after_s == 600.0


@respx.mock
async def test_retry_after_capped_at_one_hour(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/p/1").respond(429, headers={"Retry-After": "999999"})
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.retry_after_s == 3600.0


@respx.mock
async def test_5xx_retries_max_three_times(rig: Rig) -> None:
    _robots()
    route = respx.get("https://shop.test/p/1").respond(502)
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.RETRY_LATER
    assert route.call_count == 4  # 1 + 3 retries


@respx.mock
async def test_skips_pdf(rig: Rig) -> None:
    _robots()
    route = respx.get("https://shop.test/ds/esp32.pdf").respond(200)
    res = await rig.fetcher.fetch("https://shop.test/ds/esp32.pdf", make_source(), rig.source_id)
    assert res.status is FetchStatus.SKIPPED_TYPE
    assert route.call_count == 0


@respx.mock
async def test_skips_binary_content_type(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/download").respond(
        200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
    )
    res = await rig.fetcher.fetch("https://shop.test/download", make_source(), rig.source_id)
    assert res.status is FetchStatus.SKIPPED_TYPE
    assert rig.raw.objects == {}


@respx.mock
async def test_body_cap_5mb(rig: Rig) -> None:
    _robots()
    big = b"<html>" + b"a" * (MAX_BODY_BYTES + 10)
    respx.get("https://shop.test/big").respond(200, content=big, headers={"content-type": "text/html"})
    res = await rig.fetcher.fetch("https://shop.test/big", make_source(), rig.source_id)
    assert res.status is FetchStatus.TOO_LARGE


@respx.mock
async def test_login_wall_flags_source(rig: Rig) -> None:
    _robots()
    html = b"""<html><head><title>Login - Shop</title></head><body>
    <form action="/login"><input name="email"><input type="password" name="pw"></form></body></html>"""
    respx.get("https://shop.test/p/1").respond(200, content=html, headers={"content-type": "text/html"})
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.SOURCE_FLAGGED
    assert "login" in (res.reason or "")
    assert rig.raw.objects == {}


@respx.mock
async def test_captcha_flags_source(rig: Rig) -> None:
    _robots()
    html = b'<html><head><title>Just a moment...</title></head><body><div class="cf-challenge"></div></body></html>'
    respx.get("https://shop.test/p/1").respond(200, content=html, headers={"content-type": "text/html"})
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.SOURCE_FLAGGED
    assert rig.state.status[rig.source_id] == "review_required"


@respx.mock
async def test_product_page_with_header_login_is_not_a_wall(rig: Rig) -> None:
    _robots()
    html = PRODUCT_HTML.replace(b"<body>", b'<body><form><input type="password"></form>')
    respx.get("https://shop.test/p/1").respond(200, content=html, headers={"content-type": "text/html"})
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.OK


@respx.mock
async def test_redirect_hops_are_robots_checked(rig: Rig) -> None:
    _robots("User-agent: *\nDisallow: /blocked/\n")
    respx.get("https://shop.test/p/1").respond(301, headers={"location": "/blocked/1"})
    target = respx.get("https://shop.test/blocked/1").respond(200)
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.ROBOTS_DISALLOWED
    assert target.call_count == 0


@respx.mock
async def test_off_source_redirect_not_followed(rig: Rig) -> None:
    _robots()
    respx.get("https://shop.test/p/1").respond(302, headers={"location": "https://evil.test/x"})
    res = await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    assert res.status is FetchStatus.OFF_SOURCE_REDIRECT


@respx.mock
async def test_crawl_delay_is_applied(rig: Rig) -> None:
    _robots("User-agent: *\nCrawl-delay: 0.4\n")
    respx.get("https://shop.test/p/1").respond(200, content=PRODUCT_HTML, headers={"content-type": "text/html"})
    respx.get("https://shop.test/p/2").respond(200, content=PRODUCT_HTML + b"x", headers={"content-type": "text/html"})
    t0 = time.monotonic()
    await rig.fetcher.fetch("https://shop.test/p/1", make_source(), rig.source_id)
    await rig.fetcher.fetch("https://shop.test/p/2", make_source(), rig.source_id)
    # source declares 10 rps, but robots Crawl-delay (0.4 s) wins
    assert time.monotonic() - t0 >= 0.39
