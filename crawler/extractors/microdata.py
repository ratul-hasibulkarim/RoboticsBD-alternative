"""Stage A.2 — schema.org microdata (itemscope / itemprop)."""

from __future__ import annotations

from crawler.extractors.html import HTMLParser, Node, absolutize, attr, text_of
from crawler.extractors.jsonld import _availability, _condition
from crawler.extractors.types import ExtractedListing
from crawler.normalizer.currency import parse_number


def _prop_value(node: Node, base: str) -> str | None:
    for a in ("content", "value"):
        v = attr(node, a)
        if v:
            return v
    if node.tag in ("a", "link"):
        return absolutize(base, attr(node, "href"))
    if node.tag in ("img", "source"):
        return absolutize(base, attr(node, "src") or attr(node, "data-src"))
    if node.tag == "meta":
        return attr(node, "content")
    return text_of(node)


def _own_props(scope: Node, name: str) -> list[Node]:
    """itemprop=name descendants that belong to this scope (not to a nested itemscope)."""
    out = []
    for n in scope.css(f'[itemprop~="{name}"]'):
        parent = n.parent
        while (
            parent is not None
            and parent.mem_id != scope.mem_id
            and "itemscope" not in parent.attributes
        ):
            parent = parent.parent
        if parent is not None and parent.mem_id == scope.mem_id:
            out.append(n)
    return out


def _first(scope: Node, name: str, base: str) -> str | None:
    for n in _own_props(scope, name):
        v = _prop_value(n, base)
        if v:
            return v
    return None


def extract(tree: HTMLParser, url: str) -> ExtractedListing | None:
    scope = None
    for n in tree.css("[itemscope][itemtype]"):
        itype = (attr(n, "itemtype") or "").lower()
        if itype.rstrip("/").endswith("schema.org/product"):
            scope = n
            break
    if scope is None:
        return None

    price = currency = None
    in_stock = condition = None
    offer_nodes = _own_props(scope, "offers")
    for off in offer_nodes or [scope]:
        p = _first(off, "price", url) or _first(off, "lowPrice", url)
        if p is not None:
            value = parse_number(p)
            if value is not None and (price is None or value < price):
                price = value
                currency = _first(off, "priceCurrency", url) or currency
        in_stock = in_stock if in_stock is not None else _availability(_first(off, "availability", url))
        condition = condition or _condition(_first(off, "itemCondition", url))

    brand = None
    brand_nodes = _own_props(scope, "brand") or _own_props(scope, "manufacturer")
    if brand_nodes:
        b = brand_nodes[0]
        brand = _first(b, "name", url) if "itemscope" in b.attributes else _prop_value(b, url)

    images = []
    for n in _own_props(scope, "image"):
        v = _prop_value(n, url)
        if v:
            v = absolutize(url, v)
            if v and v not in images:
                images.append(v)

    gtin = _first(scope, "gtin13", url) or _first(scope, "gtin", url) or _first(scope, "gtin12", url)
    return ExtractedListing(
        url=url,
        title=_first(scope, "name", url),
        mpn=_first(scope, "mpn", url),
        manufacturer=brand,
        gtin=("".join(c for c in gtin if c.isdigit()) or None) if gtin else None,
        sku=_first(scope, "sku", url),
        price=price,
        currency=currency,
        in_stock=in_stock,
        condition=condition,  # type: ignore[arg-type]
        image_urls=images,
        snippet=_first(scope, "description", url),
        category_hint=_first(scope, "category", url),
        methods=["microdata"],
    )
