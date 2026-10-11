"""Extraction pipeline: rules first (per-source → JSON-LD → microdata → OpenGraph), LLM second."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from crawler.extractors import jsonld, microdata, opengraph, per_source
from crawler.extractors.html import HTMLParser, parse
from crawler.extractors.llm import BudgetExceededError, LlmExtractor, LlmResult
from crawler.extractors.pii import is_personal_page, scrub
from crawler.extractors.types import ExtractedListing
from crawler.normalizer.country import to_iso2
from crawler.normalizer.gtin import normalize_gtin
from crawler.normalizer.mpn import guess_mpn, looks_like_mpn, normalize_manufacturer, normalize_mpn
from crawler.normalizer.units import canonical_key
from crawler.registry import SourceConfig

MAX_IMAGES = 10


class Outcome(enum.StrEnum):
    OK = "ok"  # rule-based extraction produced an offer
    OK_LLM = "ok_llm"  # LLM produced an offer with confidence ≥ threshold
    REVIEW = "review"  # LLM below threshold → review_queue
    NO_PRODUCT = "no_product"  # not a product page (category, blog, ...)
    PERSONAL_DATA = "personal_data"  # dropped (LEGAL rule 6)
    LLM_PAUSED = "llm_paused"  # rules failed and LLM budget exhausted → retry tomorrow
    LLM_DISABLED = "llm_disabled"  # rules failed and no LLM configured


@dataclass(frozen=True)
class ExtractionResult:
    outcome: Outcome
    listing: ExtractedListing | None
    llm: LlmResult | None = None

    @property
    def committable(self) -> bool:
        return self.outcome in (Outcome.OK, Outcome.OK_LLM) and self.listing is not None


def extract_rules(tree: HTMLParser, url: str, source: SourceConfig) -> ExtractedListing | None:
    """Stage A. Higher-priority extractors win per field; lower ones fill gaps."""
    results: list[ExtractedListing] = []
    ps = per_source.get(source.extractor)
    if ps is not None:
        fn, _ = ps
        r = fn(tree, url, source.currency)
        if r is not None:
            results.append(r)
    for mod in (jsonld, microdata, opengraph):
        r = mod.extract(tree, url)
        if r is not None:
            results.append(r)
    if not results:
        return None
    merged = results[0]
    for r in results[1:]:
        merged = merged.merge_missing(r)
    return merged


def _spec_lookup(specs: dict[str, str], *keys: str) -> str | None:
    for label, value in specs.items():
        if canonical_key(label) in keys:
            return value
    return None


def finalize(listing: ExtractedListing, source: SourceConfig) -> ExtractedListing:
    """Normalise, fill defaults from the source, and scrub PII. Pure function."""
    data = listing.model_dump()
    specs = {k: scrub(v) or "" for k, v in listing.specs.items()}
    specs = {k: v for k, v in specs.items() if v}
    data["specs"] = specs
    data["snippet"] = scrub(listing.snippet)
    data["title"] = " ".join(listing.title.split()) if listing.title else None

    mpn = listing.mpn or _spec_lookup(specs, "mpn", "model")
    if mpn and not looks_like_mpn(mpn.split()[0] if " " in mpn else mpn):
        mpn = None
    if not mpn and listing.title:
        mpn = guess_mpn(listing.title)
    data["mpn"] = normalize_mpn(mpn) if mpn else None

    manufacturer = listing.manufacturer or _spec_lookup(specs, "manufacturer")
    # 'Generic', 'No brand', 'OEM' … carry no information.
    data["manufacturer"] = manufacturer if normalize_manufacturer(manufacturer) else None
    data["gtin"] = normalize_gtin(listing.gtin)
    data["package"] = listing.package or _spec_lookup(specs, "package")

    if listing.price is not None and not listing.currency:
        data["currency"] = source.currency
    if listing.moq is None:
        data["moq"] = 1
    if not listing.ships_to:
        data["ships_to"] = list(source.ships_to)
    if not listing.ships_from:
        data["ships_from"] = source.warehouse.country if source.warehouse else source.country
    else:
        data["ships_from"] = to_iso2(listing.ships_from) or listing.ships_from

    if listing.condition is None:
        title = (listing.title or "").lower()
        if re.search(r"\b(used|second[- ]hand|pre-owned)\b", title):
            data["condition"] = "used"
        elif re.search(r"\brefurb", title):
            data["condition"] = "refurb"
        else:
            data["condition"] = "new"

    data["image_urls"] = [u for u in listing.image_urls if u.startswith(("http://", "https://"))][:MAX_IMAGES]
    if listing.datasheet_url and not listing.datasheet_url.startswith(("http://", "https://")):
        data["datasheet_url"] = None
    return ExtractedListing.model_validate(data)


async def extract(
    html: str | bytes,
    url: str,
    source: SourceConfig,
    *,
    llm: LlmExtractor | None = None,
    min_confidence: float = 0.85,
) -> ExtractionResult:
    tree = parse(html)
    if is_personal_page(tree, url):
        return ExtractionResult(Outcome.PERSONAL_DATA, None)

    rules = extract_rules(tree, url, source)
    if rules is not None and rules.is_offer:
        return ExtractionResult(Outcome.OK, finalize(rules, source))

    looks_like_product = rules is not None or tree.css_first(
        'meta[property="og:type"][content="product"], [itemtype*="schema.org/Product"]'
    ) is not None
    if not looks_like_product:
        return ExtractionResult(Outcome.NO_PRODUCT, None)

    if llm is None:
        return ExtractionResult(Outcome.LLM_DISABLED, finalize(rules, source) if rules else None)

    try:
        result = await llm.extract(parse(html), url)
    except BudgetExceededError:
        return ExtractionResult(Outcome.LLM_PAUSED, None)

    if result.listing is None:
        return ExtractionResult(Outcome.REVIEW, None, result)
    merged = result.listing.merge_missing(rules) if rules else result.listing
    final = finalize(merged, source)
    if result.confidence >= min_confidence and final.is_offer:
        return ExtractionResult(Outcome.OK_LLM, final, result)
    return ExtractionResult(Outcome.REVIEW, final, result)
