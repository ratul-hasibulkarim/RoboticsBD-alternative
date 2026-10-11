"""Per-platform / per-source HTML extractors. Each module exposes
`extract(tree, url, default_currency) -> ExtractedListing | None` and a VERSION string
(bump it whenever selectors change; it is recorded in listings.extraction_method).
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

from crawler.extractors.html import HTMLParser
from crawler.extractors.per_source import opencart, shopify, woocommerce
from crawler.extractors.types import ExtractedListing

Extractor = Callable[[HTMLParser, str, str | None], ExtractedListing | None]

_MODULES: dict[str, ModuleType] = {
    "woocommerce": woocommerce,
    "opencart": opencart,
    "shopify": shopify,
}


def get(name: str) -> tuple[Extractor, str] | None:
    mod = _MODULES.get(name)
    if mod is None:
        return None
    return mod.extract, f"{name}@{mod.VERSION}"


def names() -> list[str]:
    return sorted(_MODULES)
