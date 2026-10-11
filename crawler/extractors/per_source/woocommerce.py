"""WooCommerce product pages (default Storefront-derived markup)."""

from __future__ import annotations

import re

from crawler.extractors.html import HTMLParser, absolutize, attr, first_text, table_specs, text_of
from crawler.extractors.types import ExtractedListing
from crawler.normalizer.currency import detect_currency, parse_number

VERSION = "1"


def _price(tree: HTMLParser) -> tuple[str | None, str | None]:
    box = tree.css_first(".summary p.price, .summary .price, p.price")
    if box is None:
        return None, None
    # On sale: <del>old</del><ins>new</ins> — take the <ins> amount.
    node = box.css_first("ins .woocommerce-Price-amount") or box.css_first(".woocommerce-Price-amount")
    if node is None:
        return text_of(box), text_of(box)
    sym = text_of(node.css_first(".woocommerce-Price-currencySymbol"))
    return text_of(node), sym


def extract(tree: HTMLParser, url: str, default_currency: str | None) -> ExtractedListing | None:
    if tree.css_first("body.woocommerce, body.single-product, .product_title, div.product.type-product") is None:
        return None
    title = first_text(tree, "h1.product_title", ".summary h1", "h1")
    price_text, symbol = _price(tree)
    price = parse_number(price_text) if price_text else None
    currency = detect_currency(symbol or price_text or "", default_currency) if price is not None else None

    stock_node = tree.css_first(".summary .stock, p.stock")
    in_stock = None
    stock_qty = None
    if stock_node is not None:
        classes = attr(stock_node, "class") or ""
        in_stock = "in-stock" in classes or ("out-of-stock" not in classes and "available-on-backorder" not in classes)
        m = re.search(r"(\d[\d,]*)\s+in stock", text_of(stock_node) or "", re.I)
        if m:
            stock_qty = int(m.group(1).replace(",", ""))
    elif tree.css_first("form.cart button.single_add_to_cart_button") is not None:
        in_stock = True

    images: list[str] = []
    for cell in tree.css(".woocommerce-product-gallery__image"):
        # full-size image is the <a href>; fall back to the <img> large-image attributes
        a, img = cell.css_first("a"), cell.css_first("img")
        href = absolutize(
            url,
            attr(a, "href") or attr(img, "data-large_image") or attr(img, "data-src") or attr(img, "src"),
        )
        if href and href not in images and not href.endswith(".svg"):
            images.append(href)

    specs = table_specs(tree, "table.woocommerce-product-attributes, table.shop_attributes")
    specs.update(table_specs(tree, "#tab-description table, .woocommerce-Tabs-panel--description table"))

    datasheet = None
    for a in tree.css(".summary a[href], #tab-description a[href], .woocommerce-Tabs-panel a[href]"):
        href = attr(a, "href") or ""
        label = (text_of(a) or "").lower()
        if href.lower().endswith(".pdf") or "datasheet" in label:
            datasheet = absolutize(url, href)
            break

    category = None
    crumbs = tree.css(".woocommerce-breadcrumb a, .posted_in a")
    if crumbs:
        category = text_of(crumbs[-1])

    return ExtractedListing(
        url=url,
        title=title,
        sku=first_text(tree, ".product_meta .sku", ".sku"),
        price=price,
        currency=currency,
        in_stock=in_stock,
        stock_qty=stock_qty,
        image_urls=images,
        specs=specs,
        datasheet_url=datasheet,
        snippet=first_text(tree, ".woocommerce-product-details__short-description", "#tab-description"),
        category_hint=category,
        methods=[f"woocommerce@{VERSION}"],
    )
