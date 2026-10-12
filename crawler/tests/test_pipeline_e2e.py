"""Seed → fetch → extract → listing + price → resolve → search documents, on Postgres + Redis."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import respx
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.models import Component, Listing, PriceCurrent, Source
from crawler.fetcher.client import build_crawler_client
from crawler.fetcher.ratelimit import HostRateLimiter
from crawler.fetcher.robots import RobotsCache
from crawler.fetcher.stores import FilesystemRawStore, PgPageStore, PgSourceStateStore
from crawler.fetcher.worker import Fetcher, FetchStatus
from crawler.ops import fetch_and_extract, purge_expired_raw, resolve_listing, source_db_id
from crawler.registry import Registry, sync_sources_to_db
from crawler.seeds.sitemap import walk_sitemaps
from crawler.tests.conftest import make_source
from price.fx import FxTable
from resolver.embedder import HashingEmbedder
from resolver.matcher import Action
from search.indexer import build_documents

pytestmark = pytest.mark.db
FIX = Path(__file__).parent / "fixtures" / "extract"
FX = FxTable(day=datetime.now(UTC).date(), per_usd={"BDT": Decimal("122")})

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://shop.test/product-sitemap.xml</loc></sitemap>
</sitemapindex>"""
PRODUCT_SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://shop.test/product/esp32-wroom-32/</loc></url>
  <url><loc>https://shop.test/product/dht22/</loc></url>
  <url><loc>https://shop.test/product/secret/</loc></url>
  <url><loc>https://shop.test/about-us/</loc></url>
</urlset>"""


@respx.mock
async def test_full_pipeline(db_sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, tmp_path: Path) -> None:
    src = make_source(extractor="woocommerce", seeds=[{"kind": "sitemap", "url": "https://shop.test/sitemap.xml"}])
    async with db_sessionmaker() as s:
        await sync_sources_to_db(s, Registry(version=1, sources=[src]))
        await s.commit()
        sid = await source_db_id(s, src.name)

    respx.get("https://shop.test/robots.txt").respond(200, text="User-agent: *\nDisallow: /product/secret/\n")
    respx.get("https://shop.test/sitemap.xml").respond(
        200, content=SITEMAP_INDEX, headers={"content-type": "application/xml"}
    )
    respx.get("https://shop.test/product-sitemap.xml").respond(
        200, content=PRODUCT_SITEMAP, headers={"content-type": "application/xml"}
    )
    respx.get("https://shop.test/product/esp32-wroom-32/").respond(
        200,
        content=(FIX / "woocommerce_esp32_wroom_32.html").read_bytes(),
        headers={"content-type": "text/html", "etag": '"e1"'},
    )
    respx.get("https://shop.test/product/dht22/").respond(
        200, content=(FIX / "woocommerce_out_of_stock_dht22.html").read_bytes(), headers={"content-type": "text/html"}
    )
    secret = respx.get("https://shop.test/product/secret/").respond(200)

    client = build_crawler_client()
    raw = FilesystemRawStore(tmp_path)
    fetcher = Fetcher(
        client=client,
        robots=RobotsCache(redis, client),
        limiter=HostRateLimiter(redis),
        pages=PgPageStore(db_sessionmaker),
        source_state=PgSourceStateStore(db_sessionmaker, redis),
        raw=raw,
    )
    urls = [u async for u in walk_sitemaps(fetcher, src, sid, ["https://shop.test/sitemap.xml"])]
    assert urls == [
        "https://shop.test/product/esp32-wroom-32/",
        "https://shop.test/product/dht22/",
        "https://shop.test/product/secret/",
    ]  # about-us filtered by product pattern

    results = [await fetch_and_extract(db_sessionmaker, fetcher, src, u, FX) for u in urls]
    assert [r.fetch_status for r in results] == [FetchStatus.OK, FetchStatus.OK, FetchStatus.ROBOTS_DISALLOWED]
    assert secret.call_count == 0

    embedder = HashingEmbedder()
    async with db_sessionmaker() as s:
        actions = []
        for r in results[:2]:
            assert r.listing_id is not None
            action, _ = await resolve_listing(s, r.listing_id, embedder, allow_untrusted_create=False)
            actions.append(action)
        # ESP32 page has a structured MPN ("Model" spec) → creates; DHT22 MPN is a title guess → deferred
        assert actions == [Action.CREATE, Action.DEFER]
        action, _cid = await resolve_listing(s, results[1].listing_id, embedder, allow_untrusted_create=True)  # type: ignore[arg-type]
        assert action is Action.CREATE
        await s.commit()

        comps = {c.slug: c for c in (await s.execute(select(Component))).scalars()}
        assert set(comps) == {"esp32-wroom-32", "dht22"}
        assert comps["esp32-wroom-32"].manufacturer == "Espressif"
        assert comps["esp32-wroom-32"].primary_image is not None
        assert comps["esp32-wroom-32"].datasheet_host == "www.espressif.com"
        pc = (
            await s.execute(
                select(PriceCurrent).join(Listing).where(Listing.component_id == comps["esp32-wroom-32"].id)
            )
        ).scalar_one()
        assert pc.currency == "BDT" and pc.price_minor == 52000
        docs = {d["slug"]: d for d in await build_documents(s)}
        assert docs["esp32-wroom-32"]["ships_to_bd"] is True and docs["esp32-wroom-32"]["in_stock"] is True
        assert docs["dht22"]["in_stock"] is False and "lowest_price_usd_minor" not in docs["dht22"]

    # Second crawl: conditional GET → 304 → no new extraction
    respx.get("https://shop.test/product/esp32-wroom-32/").respond(304)
    again = await fetch_and_extract(db_sessionmaker, fetcher, src, urls[0], FX)
    assert again.fetch_status is FetchStatus.NOT_MODIFIED and again.listing_id is None

    # Raw pages are purged after their TTL (LEGAL rule 7)
    async with db_sessionmaker() as s:
        from sqlalchemy import update

        from common.models import CrawlPage

        await s.execute(update(CrawlPage).values(expires_at=datetime(2000, 1, 1, tzinfo=UTC)))
        n = await purge_expired_raw(s, raw.delete)
        await s.commit()
        assert n == 4  # 2 sitemaps + 2 product pages
        assert (
            await s.execute(select(func.count()).select_from(CrawlPage).where(CrawlPage.raw_ref.is_not(None)))
        ).scalar() == 0
        assert not any(tmp_path.rglob("*.html"))  # noqa: ASYNC240 — test assertion
    await client.aclose()


@respx.mock
async def test_403_flips_source_in_db(
    db_sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, tmp_path: Path
) -> None:
    src = make_source()
    async with db_sessionmaker() as s:
        await sync_sources_to_db(s, Registry(version=1, sources=[src]))
        await s.commit()
    respx.get("https://shop.test/robots.txt").respond(200, text="")
    respx.get("https://shop.test/p/1").respond(403)
    client = build_crawler_client()
    fetcher = Fetcher(
        client=client,
        robots=RobotsCache(redis, client),
        limiter=HostRateLimiter(redis),
        pages=PgPageStore(db_sessionmaker),
        source_state=PgSourceStateStore(db_sessionmaker, redis),
        raw=FilesystemRawStore(tmp_path),
    )
    r = await fetch_and_extract(db_sessionmaker, fetcher, src, "https://shop.test/p/1", FX)
    assert r.fetch_status is FetchStatus.SOURCE_FLAGGED
    async with db_sessionmaker() as s:
        row = (await s.execute(select(Source).where(Source.name == src.name))).scalar_one()
        assert row.crawl_status == "review_required" and "403" in (row.crawl_status_reason or "")
    await client.aclose()
