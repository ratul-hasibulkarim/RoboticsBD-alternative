"""In-memory ComponentIndex used by the R1/R2/R3 tests (mirrors PgComponentIndex semantics)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from crawler.normalizer.mpn import manufacturer_key, mpn_key, mpn_match_key, normalize_manufacturer
from resolver.matcher import Candidate, Decision, ListingFeatures
from resolver.service import NewComponent


@dataclass
class MemoryIndex:
    components: dict[uuid.UUID, Candidate] = field(default_factory=dict)
    assignments: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    reviews: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    audit_rows: list[dict[str, Any]] = field(default_factory=list)

    async def candidates(self, f: ListingFeatures) -> list[Candidate]:
        out = []
        keys = set(f.title_keys)
        if f.mpn:
            keys |= {mpn_key(f.mpn), mpn_match_key(f.mpn)}
        prefix = mpn_match_key(f.mpn)[:5] if f.mpn else None
        for c in self.components.values():
            ck = mpn_key(c.mpn)
            if (f.gtin and c.gtin == f.gtin) or ck in keys or (prefix and len(prefix) == 5 and ck.startswith(prefix)):
                out.append(c)
        if f.embedding is not None:
            from resolver.embedder import cosine

            ranked = sorted(
                (c for c in self.components.values() if c.embedding is not None),
                key=lambda c: cosine(f.embedding or [], c.embedding or []),
                reverse=True,
            )[:10]
            out.extend(c for c in ranked if c not in out)
        return out

    async def create(self, c: NewComponent) -> uuid.UUID:
        mfr = normalize_manufacturer(c.manufacturer) or None
        for existing in self.components.values():  # unique (mpn_norm, manufacturer_norm)
            if mpn_key(existing.mpn) == mpn_key(c.mpn) and manufacturer_key(existing.manufacturer) == manufacturer_key(mfr):
                return existing.id
        cid = uuid.uuid4()
        self.components[cid] = Candidate(
            id=cid, mpn=c.mpn, manufacturer=mfr, gtin=c.gtin, package=c.package,
            specs_norm=c.specs_norm, embedding=c.embedding,
        )
        return cid

    async def attach(self, listing_id: uuid.UUID, component_id: uuid.UUID, confidence: float, method: str) -> None:
        self.assignments[listing_id] = component_id

    async def review(self, listing_id: uuid.UUID, decision: Decision, payload: dict[str, Any]) -> None:
        self.reviews[listing_id] = payload

    async def audit(self, action: str, **kw: Any) -> None:
        self.audit_rows.append({"action": action, **kw})
