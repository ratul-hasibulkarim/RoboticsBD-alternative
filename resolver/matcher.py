"""Entity-resolution cascade (spec §6.1 with v1.1 thresholds). Pure functions, no I/O.

Cascade — the first step that produces a confident match wins:
  1. GTIN exact                                         → 1.00  gtin
  2. MPN exact + manufacturer exact                     → 0.98  mpn_exact
     MPN exact, listing manufacturer unknown, 1 candidate → 0.90  mpn_exact
  3. MPN exact + manufacturer fuzzy (Levenshtein ≤ 2)   → 0.90  mpn_mfr_fuzzy
  4. MPN fuzzy (≤ 1 edit, len ≥ 6) + manufacturer exact → 0.85  mpn_fuzzy  → REVIEW (v1.1)
  5. embedding cosine ≥ 0.92 AND spec overlap ≥ 0.8     → 0.80  embedding
  6. otherwise: create a new component when the listing carries a trustworthy MPN,
     else send it to manual review.

Guards (§6.3):
  * different package values block every step except an exact MPN (steps 1–3);
  * different manufacturers block every step except GTIN.

Decisions:
  * confidence ≥ ATTACH_THRESHOLD (0.85) → attach listing to the component
  * REVIEW_FLOOR (0.80) ≤ confidence < 0.85 → review_queue (with the suggestion)
  * merging two *components* needs ≥ MERGE_THRESHOLD (0.95) — see `should_merge`.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from crawler.normalizer.mpn import manufacturer_key, mpn_match_key
from crawler.normalizer.units import spec_overlap
from resolver.embedder import cosine

ATTACH_THRESHOLD = 0.85
REVIEW_FLOOR = 0.80
MERGE_THRESHOLD = 0.95
EMBED_MIN_COSINE = 0.92
SPEC_MIN_OVERLAP = 0.8
FUZZY_MPN_MIN_LEN = 6


class Action(enum.StrEnum):
    ATTACH = "attach"
    CREATE = "create"
    REVIEW = "review"
    DEFER = "defer"  # title-only listing with no match yet: retry later, then create


@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    mpn: str
    manufacturer: str | None
    gtin: str | None = None
    package: str | None = None
    specs_norm: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    @property
    def mpn_key(self) -> str:
        return mpn_match_key(self.mpn)

    @property
    def mfr_key(self) -> str:
        return manufacturer_key(self.manufacturer)


@dataclass(frozen=True)
class ListingFeatures:
    mpn: str | None
    mpn_trusted: bool  # came from a structured field (JSON-LD mpn, API) rather than a title guess
    manufacturer: str | None
    gtin: str | None
    package: str | None
    title: str
    specs_norm: dict[str, Any]
    embedding: list[float] | None
    title_keys: frozenset[str] = frozenset()

    @property
    def mpn_key(self) -> str:
        return mpn_match_key(self.mpn) if self.mpn else ""

    @property
    def mfr_key(self) -> str:
        return manufacturer_key(self.manufacturer)


@dataclass(frozen=True)
class Decision:
    action: Action
    component_id: uuid.UUID | None
    confidence: float
    method: str
    reason: str


def _package_key(p: str | None) -> str:
    if not p:
        return ""
    import re

    return re.sub(r"[^a-z0-9]", "", p.lower())


def _packages_conflict(a: str | None, b: str | None) -> bool:
    ka, kb = _package_key(a), _package_key(b)
    return bool(ka and kb and ka != kb)


def _mfr_conflict(a: str, b: str) -> bool:
    return bool(a and b and a != b)


def spec_evidence(a: dict[str, Any], b: dict[str, Any]) -> tuple[int, float]:
    shared = len((a.keys() & b.keys()) - {"manufacturer", "model", "mpn"})
    return shared, spec_overlap(a, b)


def _lev(a: str, b: str, k: int) -> bool:
    from rapidfuzz.distance import Levenshtein

    return bool(Levenshtein.distance(a, b, score_cutoff=k) <= k)


def refine_untrusted_mpn(listing: ListingFeatures, candidates: list[Candidate]) -> ListingFeatures:
    """For an MPN guessed from a title, prefer the longest known component MPN spelled in the
    title (with or without spaces): 'ESP32 WROOM 32 module' → ESP32-WROOM-32."""
    if listing.mpn_trusted or not listing.title_keys:
        return listing
    hits = [c for c in candidates if c.mpn_key and c.mpn_key in listing.title_keys]
    if not hits:
        return listing
    best = max(hits, key=lambda c: len(c.mpn_key))
    guessed_is_known = any(c.mpn_key == listing.mpn_key for c in candidates)
    if not guessed_is_known or len(best.mpn_key) > len(listing.mpn_key):
        return replace(listing, mpn=best.mpn)
    return listing


def match(listing: ListingFeatures, candidates: list[Candidate], *, allow_untrusted_create: bool = True) -> Decision:
    listing = refine_untrusted_mpn(listing, candidates)
    lk, lm = listing.mpn_key, listing.mfr_key

    # A guessed base MPN ('AMS1117') when variants exist ('AMS1117-3.3', 'AMS1117-5.0')
    # is ambiguous: never attach or create, ask a human.
    if lk and not listing.mpn_trusted and not listing.gtin and not any(c.mpn_key == lk for c in candidates):
        variants = {c.mpn_key for c in candidates if c.mpn_key.startswith(lk)}
        if variants:
            return Decision(
                Action.REVIEW, None, 0.0, "none", f"guessed MPN {listing.mpn} is a prefix of {len(variants)} parts"
            )

    # 1. GTIN
    if listing.gtin:
        for c in candidates:
            if c.gtin and c.gtin == listing.gtin:
                return Decision(Action.ATTACH, c.id, 1.0, "gtin", "GTIN exact")

    if lk:
        exact = [c for c in candidates if c.mpn_key == lk]
        # 2. MPN exact + manufacturer exact
        if lm:
            for c in exact:
                if c.mfr_key == lm:
                    return Decision(Action.ATTACH, c.id, 0.98, "mpn_exact", "MPN + manufacturer exact")
        else:
            if len(exact) == 1:
                return Decision(
                    Action.ATTACH, exact[0].id, 0.90, "mpn_exact", "MPN exact; listing manufacturer unknown"
                )
            if len(exact) > 1:
                return Decision(Action.REVIEW, None, 0.0, "mpn_exact", f"MPN matches {len(exact)} manufacturers")
        # 3. MPN exact + manufacturer fuzzy
        if lm:
            for c in exact:
                if c.mfr_key and _lev(c.mfr_key, lm, 2):
                    return Decision(Action.ATTACH, c.id, 0.90, "mpn_mfr_fuzzy", "MPN exact, manufacturer ≤2 edits")
            # candidate has no manufacturer but listing does: same as step-2 "unknown" case
            unknown = [c for c in exact if not c.mfr_key]
            if len(unknown) == 1 and len(exact) == 1:
                return Decision(
                    Action.ATTACH, unknown[0].id, 0.90, "mpn_exact", "MPN exact; component manufacturer unknown"
                )

        # 4. MPN fuzzy + manufacturer exact (+ package must not conflict). Only for MPNs guessed
        #    from titles: a distributor/API MPN is never a typo.
        if lm and len(lk) >= FUZZY_MPN_MIN_LEN and not listing.mpn_trusted:
            for c in candidates:
                if c.mpn_key == lk or c.mfr_key != lm or len(c.mpn_key) < FUZZY_MPN_MIN_LEN:
                    continue
                if _packages_conflict(listing.package, c.package):
                    continue
                if not _lev(c.mpn_key, lk, 1):
                    continue
                # One character often IS a different part (ATmega328 vs ATmega328P, …-32 vs
                # …-32D). Require positive evidence: ≥ 2 shared spec keys that agree.
                shared, overlap = spec_evidence(listing.specs_norm, c.specs_norm)
                if shared < 2 or overlap < SPEC_MIN_OVERLAP:
                    continue
                # A pure suffix/prefix extension is a variant, never a typo.
                if lk.startswith(c.mpn_key) or c.mpn_key.startswith(lk):
                    continue
                # v1.1: one character usually IS a different part (CH340C/G, BMP280/BME280),
                # so a fuzzy MPN is a suggestion for a human, never an automatic attach.
                return Decision(Action.REVIEW, c.id, 0.85, "mpn_fuzzy", "MPN 1 edit, manufacturer exact")

    # 5. Embedding + spec overlap → below attach threshold → review with suggestion
    if listing.embedding is not None:
        best: tuple[float, Candidate] | None = None
        for c in candidates:
            if c.embedding is None:
                continue
            if _mfr_conflict(lm, c.mfr_key) or _packages_conflict(listing.package, c.package):
                continue
            if lk and c.mpn_key and lk != c.mpn_key:
                continue  # two different, known MPNs are never the same part via embeddings
            sim = cosine(listing.embedding, c.embedding)
            if sim >= EMBED_MIN_COSINE and spec_overlap(listing.specs_norm, c.specs_norm) >= SPEC_MIN_OVERLAP:
                if best is None or sim > best[0]:
                    best = (sim, c)
        if best is not None:
            return Decision(Action.REVIEW, best[1].id, REVIEW_FLOOR, "embedding", f"embedding cosine {best[0]:.3f}")

    # 6. New component or manual review
    if lk and listing.mpn_trusted:
        return Decision(Action.CREATE, None, 1.0, "new", "no existing component; trusted MPN")
    if lk and not any(c.mpn_key == lk for c in candidates):
        # Trusted-first: give distributor/API/JSON-LD listings time to create the canonical
        # component before a title guess does (a title guess can pick the wrong token).
        if not allow_untrusted_create:
            return Decision(Action.DEFER, None, 0.0, "none", "title-only MPN; waiting for a trusted source")
        return Decision(Action.CREATE, None, 1.0, "new", "no existing component; MPN guessed from title")
    return Decision(Action.REVIEW, None, 0.0, "none", "no MPN and no confident match")


def should_merge(a: Candidate, b: Candidate) -> tuple[bool, float, str]:
    """Merge two *components*? Only at ≥ 0.95 (GTIN, or MPN+manufacturer exact)."""
    if a.gtin and b.gtin and a.gtin == b.gtin:
        return True, 1.0, "gtin"
    if a.mpn_key and a.mpn_key == b.mpn_key and a.mfr_key and a.mfr_key == b.mfr_key:
        return True, 0.98, "mpn_exact"
    return False, 0.0, ""
