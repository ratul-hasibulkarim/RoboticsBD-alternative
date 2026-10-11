"""Sitemap / category walkers. Every fetch goes through the polite Fetcher (robots, rate limit)."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from xml.etree import ElementTree as ET  # noqa: S405 — parsing only; no entity expansion in stdlib ET

from crawler.extractors.html import absolutize, attr, parse
from crawler.fetcher.worker import Fetcher, FetchStatus
from crawler.registry import SourceConfig

_NS = re.compile(r"\{[^}]+\}")
MAX_SITEMAPS = 200
MAX_URLS = 100_000

# Product URL patterns per platform extractor; "generic" accepts everything from the sitemap.
PRODUCT_PATTERNS: dict[str, re.Pattern[str]] = {
    "woocommerce": re.compile(r"/product/[^/]+/?$"),
    "opencart": re.compile(r"(route=product/product|product_id=\d+|/index\.php\?.*product)"),
    "shopify": re.compile(r"/products/[^/?#]+$"),
}


def parse_sitemap(xml: bytes) -> tuple[list[str], list[str]]:
    """Return (child sitemaps, page urls). Rejects DTDs (no XXE / billion-laughs)."""
    if b"<!DOCTYPE" in xml[:2048] or b"<!ENTITY" in xml[:4096]:
        return [], []
    try:
        root = ET.fromstring(xml)  # noqa: S314
    except ET.ParseError:
        return [], []
    tag = _NS.sub("", root.tag)
    locs = [(_NS.sub("", el.tag), (el.text or "").strip()) for el in root.iter() if _NS.sub("", el.tag) == "loc"]
    urls = [u for _, u in locs if u]
    if tag == "sitemapindex":
        return urls, []
    return [], urls


def is_product_url(source: SourceConfig, url: str) -> bool:
    pat = PRODUCT_PATTERNS.get(source.extractor)
    return True if pat is None else bool(pat.search(url))


async def walk_sitemaps(
    fetcher: Fetcher, source: SourceConfig, source_id: uuid.UUID, roots: list[str]
) -> AsyncIterator[str]:
    """Yield product URLs from sitemap roots (follows sitemap indexes)."""
    queue = list(roots)
    seen_maps: set[str] = set()
    emitted = 0
    while queue and len(seen_maps) < MAX_SITEMAPS:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        res = await fetcher.fetch(sm, source, source_id)
        if res.status not in (FetchStatus.OK, FetchStatus.UNCHANGED, FetchStatus.NOT_MODIFIED) or res.body is None:
            continue
        children, urls = parse_sitemap(res.body)
        queue.extend(c for c in children if c not in seen_maps)
        for u in urls:
            if is_product_url(source, u):
                yield u
                emitted += 1
                if emitted >= MAX_URLS:
                    return


async def walk_category(
    fetcher: Fetcher, source: SourceConfig, source_id: uuid.UUID, start: str, max_pages: int = 50
) -> AsyncIterator[str]:
    """Follow product links and rel=next pagination on category pages."""
    url: str | None = start
    pages = 0
    seen: set[str] = set()
    while url and pages < max_pages:
        res = await fetcher.fetch(url, source, source_id)
        pages += 1
        if res.body is None:
            return
        tree = parse(res.body)
        for a in tree.css("a[href]"):
            href = absolutize(res.final_url, attr(a, "href"))
            if href and href not in seen and is_product_url(source, href):
                seen.add(href)
                yield href
        nxt = tree.css_first('link[rel="next"], a[rel="next"], a.next')
        url = absolutize(res.final_url, attr(nxt, "href")) if nxt is not None else None
