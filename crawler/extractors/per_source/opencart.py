"""OpenCart 2.x/3.x product pages (default theme markup)."""

from __future__ import annotations

import re

from crawler.extractors.html import HTMLParser, absolutize, attr, first_text, table_specs, text_of
from crawler.extractors.types import ExtractedListing
from crawler.normalizer.currency import detect_currency, parse_number

VERSION = "1"


def _meta_list(tree: HTMLParser) -> dict[str, str]:
    """`<ul class="list-unstyled"><li>Product Code: X</li><li>Availability: In Stock</li>`."""
    out: dict[str, str] = {}
    for li in tree.css("#product-product ul.list-unstyled li, #content .col-sm-4 ul.list-unstyled li, #content ul.list-unstyled li"):
        t = text_of(li) or ""
        if ":" in t:
            k, _, v = t.partition(":")
            out.setdefault(k.strip().lower(), v.strip())
    return out


def extract(tree: HTMLParser, url: str, default_currency: str | None) -> ExtractedListing | None:
    if tree.css_first("#product-product, #product, input[name=product_id]") is None:
        return None
    meta = _meta_list(tree)
    title = first_text(tree, "#content h1", "h1")
    price_text = (
        first_text(tree, "#content .price-new", "#content ul.list-unstyled h2", ".product-price", "#content .price")
        or meta.get("price")
    )
    price = parse_number(price_text) if price_text else None
    currency = detect_currency(price_text or "", default_currency) if price is not None else None

    availability = (meta.get("availability") or "").lower()
    in_stock: bool | None = None
    stock_qty = None
    if availability:
        m = re.match(r"(\d+)", availability)
        if m:
            stock_qty = int(m.group(1))
            in_stock = stock_qty > 0
        else:
            in_stock = "in stock" in availability or "available" in availability
            if "out of stock" in availability or "pre-order" in availability:
                in_stock = False

    moq = None
    m = re.search(r"minimum quantity of (\d+)", text_of(tree.css_first("#product .alert-info, .minimum")) or "", re.I)
    if m:
        moq = int(m.group(1))

    images: list[str] = []
    for a in tree.css("ul.thumbnails a.thumbnail, .thumbnails a"):
        href = absolutize(url, attr(a, "href"))
        if href and href not in images:
            images.append(href)

    specs = table_specs(tree, "#tab-specification table")
    specs.update(table_specs(tree, "#tab-description table"))

    datasheet = None
    for a in tree.css("#tab-description a[href]"):
        href = attr(a, "href") or ""
        if href.lower().endswith(".pdf") or "datasheet" in (text_of(a) or "").lower():
            datasheet = absolutize(url, href)
            break

    crumbs = tree.css("ul.breadcrumb li a")
    category = text_of(crumbs[-2]) if len(crumbs) >= 2 else None

    return ExtractedListing(
        url=url,
        title=title,
        sku=meta.get("product code") or meta.get("model"),
        manufacturer=meta.get("brand"),
        price=price,
        currency=currency,
        moq=moq,
        in_stock=in_stock,
        stock_qty=stock_qty,
        image_urls=images,
        specs=specs,
        datasheet_url=datasheet,
        snippet=first_text(tree, "#tab-description"),
        category_hint=category,
        methods=[f"opencart@{VERSION}"],
    )
