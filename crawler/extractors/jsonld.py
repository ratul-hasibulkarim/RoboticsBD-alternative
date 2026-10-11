"""Stage A.1 — schema.org JSON-LD (Product / Offer / AggregateOffer / PriceSpecification)."""

from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from crawler.extractors.html import HTMLParser, absolutize
from crawler.extractors.types import ExtractedListing, PriceBreak
from crawler.normalizer.country import to_iso2
from crawler.normalizer.currency import parse_number

_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _loads_lenient(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("<!--"):
        raw = raw.removeprefix("<!--").removesuffix("-->")
    for candidate in (
        raw,
        _CONTROL.sub(" ", raw),
        _TRAILING_COMMA.sub(r"\1", _CONTROL.sub(" ", raw)),
        _TRAILING_COMMA.sub(r"\1", _CONTROL.sub(" ", html_lib.unescape(raw))),
    ):
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
    return None


def _types(node: dict[str, Any]) -> set[str]:
    t = node.get("@type", [])
    if isinstance(t, str):
        t = [t]
    return {str(x).rsplit("/", 1)[-1].lower() for x in t if x}


def iter_nodes(data: Any) -> Iterator[dict[str, Any]]:
    """Walk JSON-LD (lists, @graph, nested objects) yielding every typed object."""
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            stack.extend(reversed(cur))
        elif isinstance(cur, dict):
            if "@type" in cur:
                yield cur
            for key in ("@graph", "mainEntity", "itemListElement", "item", "hasVariant"):
                if key in cur:
                    stack.append(cur[key])


def blocks(tree: HTMLParser) -> list[Any]:
    out = []
    for node in tree.css('script[type="application/ld+json"]'):
        data = _loads_lenient(node.text(deep=True))
        if data is not None:
            out.append(data)
    return out


def _str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, dict):
        return _str(v.get("name") or v.get("@value") or v.get("value"))
    if isinstance(v, list):
        return _str(v[0]) if v else None
    s = " ".join(html_lib.unescape(str(v)).split())
    return s or None


def _images(v: Any, base: str) -> list[str]:
    items = v if isinstance(v, list) else [v]
    out: list[str] = []
    for it in items:
        url = it.get("contentUrl") or it.get("url") if isinstance(it, dict) else it
        abs_url = absolutize(base, _str(url))
        if abs_url and abs_url not in out:
            out.append(abs_url)
    return out


def _availability(v: Any) -> bool | None:
    s = (_str(v) or "").lower()
    if not s:
        return None
    if any(k in s for k in ("instock", "in stock", "limitedavailability", "onlineonly", "instoreonly")):
        return True
    if any(k in s for k in ("outofstock", "soldout", "discontinued", "preorder", "backorder")):
        return False
    return None


def _condition(v: Any) -> str | None:
    s = (_str(v) or "").lower()
    if "new" in s:
        return "new"
    if "used" in s:
        return "used"
    if "refurb" in s:
        return "refurb"
    return None


def _decimal(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return Decimal(str(v))
    return parse_number(str(v))


def _offers(node: dict[str, Any]) -> list[dict[str, Any]]:
    o = node.get("offers")
    if o is None:
        return []
    items = o if isinstance(o, list) else [o]
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if "aggregateoffer" in _types(it) and isinstance(it.get("offers"), list | dict):
            nested = it["offers"] if isinstance(it["offers"], list) else [it["offers"]]
            out.extend(x for x in nested if isinstance(x, dict))
        # the aggregate itself is kept too: its lowPrice covers nested offers without price
        out.append(it)
    return out


def _price_breaks(offer: dict[str, Any]) -> list[PriceBreak]:
    specs = offer.get("priceSpecification")
    items = specs if isinstance(specs, list) else ([specs] if specs else [])
    breaks: list[PriceBreak] = []
    for sp in items:
        if not isinstance(sp, dict):
            continue
        price = _decimal(sp.get("price"))
        qty_node = sp.get("eligibleQuantity") or {}
        qty = qty_node.get("minValue") if isinstance(qty_node, dict) else None
        if price is not None and qty is not None:
            q = _decimal(qty)
            if q is not None and q >= 1:
                breaks.append(PriceBreak(qty=int(q), price=price))
    return sorted(set(breaks), key=lambda b: b.qty)


def _ships_to(offer: dict[str, Any]) -> list[str]:
    details = offer.get("shippingDetails")
    items = details if isinstance(details, list) else ([details] if details else [])
    out: list[str] = []
    for d in items:
        if not isinstance(d, dict):
            continue
        dest = d.get("shippingDestination")
        dests = dest if isinstance(dest, list) else [dest]
        for x in dests:
            code = to_iso2(_str(x.get("addressCountry")) if isinstance(x, dict) else _str(x))
            if code and code not in out:
                out.append(code)
    return out


def _additional_properties(node: dict[str, Any]) -> dict[str, str]:
    props = node.get("additionalProperty") or []
    props = props if isinstance(props, list) else [props]
    out: dict[str, str] = {}
    for p in props:
        if isinstance(p, dict):
            name, value = _str(p.get("name")), _str(p.get("value"))
            unit = _str(p.get("unitText") or p.get("unitCode"))
            if name and value:
                out[name] = f"{value} {unit}" if unit and unit not in value else value
    return out


def _product_from_node(node: dict[str, Any], url: str) -> ExtractedListing:
    offers = _offers(node)
    price = currency = None
    in_stock = None
    condition = None
    breaks: list[PriceBreak] = []
    moq = None
    ships_to: list[str] = []
    ships_from = None
    stock_qty: int | None = None
    for off in offers:
        p = _decimal(off.get("price"))
        if p is None:
            p = _decimal(off.get("lowPrice"))
        spec = off.get("priceSpecification")
        if p is None and isinstance(spec, dict):
            p = _decimal(spec.get("price"))
        cur = _str(off.get("priceCurrency")) or (
            _str(spec.get("priceCurrency")) if isinstance(spec, dict) else None
        )
        if p is not None and (price is None or p < price):
            price, currency = p, cur or currency
        in_stock = in_stock if in_stock is not None else _availability(off.get("availability"))
        condition = condition or _condition(off.get("itemCondition"))
        breaks = breaks or _price_breaks(off)
        eq = off.get("eligibleQuantity")
        if moq is None and isinstance(eq, dict) and _decimal(eq.get("minValue")):
            moq = int(_decimal(eq.get("minValue")) or 1)
        ships_to = ships_to or _ships_to(off)
        inv = off.get("inventoryLevel")
        if stock_qty is None and inv is not None:
            q = _decimal(inv.get("value") if isinstance(inv, dict) else inv)
            stock_qty = int(q) if q is not None else None
        seller_addr = off.get("availableAtOrFrom") or {}
        if isinstance(seller_addr, dict) and not ships_from:
            addr = seller_addr.get("address") or {}
            ships_from = to_iso2(_str(addr.get("addressCountry")) if isinstance(addr, dict) else None)
    if breaks and price is None:
        price = breaks[0].price
    if breaks and moq is None:
        moq = breaks[0].qty

    gtin = None
    for key in ("gtin13", "gtin", "gtin12", "gtin14", "gtin8", "isbn"):
        gtin = _str(node.get(key))
        if gtin:
            gtin = re.sub(r"\D", "", gtin) or None
            if gtin:
                break

    return ExtractedListing(
        url=url,
        title=_str(node.get("name")),
        mpn=_str(node.get("mpn")),
        manufacturer=_str(node.get("manufacturer")) or _str(node.get("brand")),
        gtin=gtin,
        sku=_str(node.get("sku")),
        price=price,
        currency=currency,
        price_breaks=breaks,
        moq=moq,
        in_stock=in_stock,
        stock_qty=stock_qty,
        condition=condition,  # type: ignore[arg-type]
        image_urls=_images(node.get("image"), url) if node.get("image") else [],
        specs=_additional_properties(node),
        category_hint=_str(node.get("category")),
        snippet=_str(node.get("description")),
        ships_from=ships_from,
        ships_to=ships_to,
        methods=["jsonld"],
    )


def extract(tree: HTMLParser, url: str) -> ExtractedListing | None:
    products: list[dict[str, Any]] = []
    for data in blocks(tree):
        for node in iter_nodes(data):
            types = _types(node)
            if types & {"product", "productgroup", "individualproduct", "productmodel"}:
                products.append(node)
    if not products:
        return None
    # Prefer the product node that actually carries offers.
    products.sort(key=lambda n: (n.get("offers") is not None, len(n)), reverse=True)
    result = _product_from_node(products[0], url)
    return result


def page_types(tree: HTMLParser) -> set[str]:
    """All @types on the page (used by the PII filter)."""
    out: set[str] = set()
    for data in blocks(tree):
        for node in iter_nodes(data):
            out |= _types(node)
    return out
