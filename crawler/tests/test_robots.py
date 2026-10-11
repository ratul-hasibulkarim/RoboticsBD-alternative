"""C1 support: robots.txt parsing, caching, and fail-closed behaviour."""

from __future__ import annotations

import httpx
import respx

from crawler.fetcher.client import build_crawler_client
from crawler.fetcher.robots import RobotsCache, fetch_robots, origin_of

ROBOTS = """
User-agent: *
Disallow: /cart
Crawl-delay: 3

User-agent: VoltFindBot
Disallow: /private/
Allow: /
Crawl-delay: 4

Sitemap: https://shop.test/sitemap.xml
"""


def test_origin_of_strips_default_ports() -> None:
    assert origin_of("https://Shop.Test:443/a?b=1") == "https://shop.test"
    assert origin_of("http://shop.test:8080/x") == "http://shop.test:8080"


@respx.mock
async def test_parsed_rules_are_obeyed() -> None:
    respx.get("https://shop.test/robots.txt").respond(200, text=ROBOTS)
    async with build_crawler_client() as c:
        rules = await fetch_robots(c, "https://shop.test")
    assert rules.state == "parsed"
    assert rules.can_fetch("https://shop.test/product/esp32")
    assert not rules.can_fetch("https://shop.test/private/x")
    assert rules.crawl_delay() == 4.0
    assert rules.sitemaps() == ["https://shop.test/sitemap.xml"]


@respx.mock
async def test_404_means_allow_all() -> None:
    respx.get("https://shop.test/robots.txt").respond(404)
    async with build_crawler_client() as c:
        rules = await fetch_robots(c, "https://shop.test")
    assert rules.state == "missing"
    assert rules.can_fetch("https://shop.test/anything")


@respx.mock
async def test_5xx_fails_closed() -> None:
    respx.get("https://shop.test/robots.txt").respond(503)
    async with build_crawler_client() as c:
        rules = await fetch_robots(c, "https://shop.test")
    assert rules.state == "unreachable"
    assert not rules.can_fetch("https://shop.test/")


@respx.mock
async def test_429_fails_closed() -> None:
    respx.get("https://shop.test/robots.txt").respond(429)
    async with build_crawler_client() as c:
        rules = await fetch_robots(c, "https://shop.test")
    assert not rules.can_fetch("https://shop.test/")


@respx.mock
async def test_network_error_fails_closed() -> None:
    respx.get("https://shop.test/robots.txt").mock(side_effect=httpx.ConnectError("boom"))
    async with build_crawler_client() as c:
        rules = await fetch_robots(c, "https://shop.test")
    assert rules.state == "unreachable"
    assert not rules.can_fetch("https://shop.test/product/1")


@respx.mock
async def test_redirect_followed() -> None:
    respx.get("http://shop.test/robots.txt").respond(301, headers={"location": "https://shop.test/robots.txt"})
    respx.get("https://shop.test/robots.txt").respond(200, text="User-agent: *\nDisallow: /")
    async with build_crawler_client() as c:
        rules = await fetch_robots(c, "http://shop.test")
    assert not rules.can_fetch("http://shop.test/x")


@respx.mock
async def test_cache_hits_redis_once(redis) -> None:  # type: ignore[no-untyped-def]
    route = respx.get("https://shop.test/robots.txt").respond(200, text=ROBOTS)
    async with build_crawler_client() as c:
        cache = RobotsCache(redis, c)
        assert await cache.can_fetch("https://shop.test/a")
        assert await cache.can_fetch("https://shop.test/b")
        assert not await cache.can_fetch("https://shop.test/private/c")
    assert route.call_count == 1
    ttl = await redis.ttl("robots:https://shop.test")
    assert 23 * 3600 < ttl <= 24 * 3600


@respx.mock
async def test_unreachable_cached_short(redis) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://shop.test/robots.txt").respond(500)
    async with build_crawler_client() as c:
        cache = RobotsCache(redis, c)
        assert not await cache.can_fetch("https://shop.test/a")
    assert await redis.ttl("robots:https://shop.test") <= 3600
