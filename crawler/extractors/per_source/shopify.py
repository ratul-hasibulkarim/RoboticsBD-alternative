"""Shopify product pages: the theme's embedded product JSON (`data-product-json` / ProductJson-*)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, cast

from crawler.extractors.html import HTMLParser, absolutize, first_text
from crawler.extractors.types import ExtractedListing
from crawler.normalizer.currency import detect_currency

VERSION = "1"


def _product_json(tree: HTMLParser) -> dict[str, Any] | None:
    for sel in (
        "script[data-product-json]",
        'script[id^="ProductJson-"]',
        'script[type="application/json"][data-product]',
    ):
        node = tree.css_first(sel)
        if node is None:
            continue
        try:
            data = json.loads(node.text(deep=True))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "variants" in data:
            return cast(dict[str, Any], data)
        if isinstance(data, dict) and isinstance(data.get("product"), dict):
            return cast(dict[str, Any], data["product"])
    return None


def extract(tree: HTMLParser, url: str, default_currency: str | None) -> ExtractedListing | None:
    data = _product_json(tree)
    if data is None:
        return None
    variants = [v for v in data.get("variants", []) if isinstance(v, dict)]
    chosen = next((v for v in variants if v.get("available")), variants[0] if variants else {})
    raw_price = chosen.get("price", data.get("price"))
    price = None
    if isinstance(raw_price, int):
        price = Decimal(raw_price) / 100  # Shopify product JSON prices are in cents
    elif isinstance(raw_price, str) and raw_price:
        price = Decimal(raw_price)
    currency_meta = tree.css_first('meta[property="og:price:currency"]')
    currency = (currency_meta.attributes.get("content") if currency_meta is not None else None) or detect_currency(
        first_text(tree, ".price, .product__price") or "", default_currency
    )

    images: list[str] = []
    for img in data.get("images", []) or []:
        src = img if isinstance(img, str) else (img.get("src") if isinstance(img, dict) else None)
        abs_src = absolutize(url, src)
        if abs_src and abs_src not in images:
            images.append(abs_src)

    qty = chosen.get("inventory_quantity")
    return ExtractedListing(
        url=url,
        title=str(data.get("title") or "") or None,
        manufacturer=str(data.get("vendor") or "") or None,
        sku=str(chosen.get("sku") or "") or None,
        gtin=str(chosen.get("barcode") or "") or None,
        price=price,
        currency=currency,
        in_stock=bool(chosen.get("available")) if "available" in chosen else None,
        stock_qty=int(qty) if isinstance(qty, int) and qty >= 0 else None,
        image_urls=images,
        category_hint=str(data.get("type") or "") or None,
        snippet=first_text(tree, ".product-single__description", ".product__description"),
        methods=[f"shopify@{VERSION}"],
    )
