"""Stage A.3 — OpenGraph / product meta tags (weakest structured signal)."""

from __future__ import annotations

from crawler.extractors.html import HTMLParser, absolutize, attr
from crawler.extractors.types import ExtractedListing
from crawler.normalizer.currency import parse_number


def _meta(tree: HTMLParser, *names: str) -> str | None:
    for name in names:
        for sel in (f'meta[property="{name}"]', f'meta[name="{name}"]', f'meta[itemprop="{name}"]'):
            v = attr(tree.css_first(sel), "content")
            if v:
                return v
    return None


def extract(tree: HTMLParser, url: str) -> ExtractedListing | None:
    og_type = (_meta(tree, "og:type") or "").lower()
    price_raw = _meta(tree, "product:price:amount", "og:price:amount", "product:sale_price:amount")
    if "product" not in og_type and price_raw is None:
        return None
    availability = (_meta(tree, "product:availability", "og:availability") or "").lower().replace(" ", "")
    in_stock = None
    if availability:
        in_stock = availability in ("instock", "in_stock", "available", "pending") or "instock" in availability
        if "oos" in availability or "outofstock" in availability:
            in_stock = False
    image = absolutize(url, _meta(tree, "og:image:secure_url", "og:image"))
    return ExtractedListing(
        url=url,
        title=_meta(tree, "og:title"),
        manufacturer=_meta(tree, "product:brand", "og:brand"),
        price=parse_number(price_raw) if price_raw else None,
        currency=_meta(tree, "product:price:currency", "og:price:currency"),
        in_stock=in_stock,
        image_urls=[image] if image else [],
        snippet=_meta(tree, "og:description", "description"),
        gtin=_meta(tree, "product:ean", "product:upc", "product:gtin"),
        mpn=_meta(tree, "product:mfr_part_no"),
        sku=_meta(tree, "product:retailer_item_id"),
        methods=["opengraph"],
    )
