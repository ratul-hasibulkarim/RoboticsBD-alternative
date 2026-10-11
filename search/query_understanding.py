"""Classify a query: exact part number, category browse, or natural language (§8.2 step 1)."""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass

from crawler.normalizer.mpn import looks_like_mpn, mpn_key, normalize_mpn
from resolver.categorize import categorize


class QueryKind(enum.StrEnum):
    MPN = "mpn"
    CATEGORY = "category"
    NATURAL = "natural"


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    norm: str
    kind: QueryKind
    mpn: str | None = None
    mpn_key: str | None = None
    category: str | None = None
    wants_bd: bool = False
    max_price_usd_minor: int | None = None


_BD_WORDS = re.compile(r"\b(bd|bangladesh|dhaka|chittagong|chattogram|sylhet|বাংলাদেশ|ঢাকা)\b", re.I)
_UNDER = re.compile(r"\b(?:under|below|less than|<)\s*\$?\s*(\d+(?:\.\d+)?)\s*(usd|\$|tk|taka|bdt|৳)?", re.I)


def normalize_query(q: str) -> str:
    q = unicodedata.normalize("NFKC", q).strip()
    return re.sub(r"\s+", " ", q)[:200]


def parse_query(q: str, *, bdt_per_usd: float = 122.0) -> ParsedQuery:
    norm = normalize_query(q)
    lowered = norm.lower()
    wants_bd = bool(_BD_WORDS.search(lowered))
    max_price = None
    m = _UNDER.search(lowered)
    if m:
        amount = float(m.group(1))
        unit = (m.group(2) or "$").lower()
        usd = amount / bdt_per_usd if unit in ("tk", "taka", "bdt", "৳") else amount
        max_price = int(usd * 100)
    cleaned = _BD_WORDS.sub(" ", _UNDER.sub(" ", norm)).strip()
    tokens = cleaned.split()
    if len(tokens) == 1 and looks_like_mpn(tokens[0]):
        return ParsedQuery(q, norm, QueryKind.MPN, normalize_mpn(tokens[0]), mpn_key(tokens[0]),
                           wants_bd=wants_bd, max_price_usd_minor=max_price)
    if len(tokens) <= 4:
        cat, _ = categorize(cleaned)
        if cat != "other" and not any(looks_like_mpn(t) for t in tokens):
            return ParsedQuery(q, norm, QueryKind.CATEGORY, category=cat, wants_bd=wants_bd,
                               max_price_usd_minor=max_price)
    mpn_tok = next((t for t in tokens if looks_like_mpn(t)), None)
    return ParsedQuery(q, norm, QueryKind.NATURAL, normalize_mpn(mpn_tok) if mpn_tok else None,
                       mpn_key(mpn_tok) if mpn_tok else None, wants_bd=wants_bd, max_price_usd_minor=max_price)
