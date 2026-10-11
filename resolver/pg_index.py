"""Postgres implementation of ComponentIndex (repository functions for the resolver)."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Datasheet, Listing, ReviewItem
from crawler.normalizer.mpn import manufacturer_key, mpn_key, mpn_match_key, normalize_manufacturer
from resolver.categorize import categorize, slugify
from resolver.matcher import Candidate, Decision, ListingFeatures
from resolver.merge_audit import write_audit
from resolver.service import NewComponent

PREFIX_LEN = 5
MAX_CANDIDATES = 50
EMBED_NEIGHBOURS = 10


def _to_candidate(c: Component) -> Candidate:
    emb = c.embedding
    return Candidate(
        id=c.id,
        mpn=c.mpn,
        manufacturer=c.manufacturer,
        gtin=c.gtin,
        package=c.package,
        specs_norm=dict(c.specs_norm or {}),
        embedding=[float(x) for x in emb] if emb is not None else None,
    )


class PgComponentIndex:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def candidates(self, f: ListingFeatures) -> list[Candidate]:
        found: dict[uuid.UUID, Component] = {}
        conds = []
        if f.gtin:
            conds.append(Component.gtin == f.gtin)
        if f.mpn:
            key, mkey = mpn_key(f.mpn), mpn_match_key(f.mpn)
            conds.append(Component.mpn_norm.in_({key, mkey}))
            if len(mkey) >= PREFIX_LEN:
                conds.append(Component.mpn_norm.like(mkey[:PREFIX_LEN] + "%"))
        if f.title_keys:
            conds.append(Component.mpn_norm.in_(sorted(f.title_keys)))
        if conds:
            rows = (
                await self.s.execute(
                    select(Component)
                    .where(Component.status == "active", or_(*conds))
                    .limit(MAX_CANDIDATES)
                )
            ).scalars()
            for c in rows:
                found[c.id] = c
        if f.embedding is not None:
            rows = (
                await self.s.execute(
                    select(Component)
                    .where(Component.status == "active", Component.embedding.is_not(None))
                    .order_by(Component.embedding.cosine_distance(f.embedding))
                    .limit(EMBED_NEIGHBOURS)
                )
            ).scalars()
            for c in rows:
                found.setdefault(c.id, c)
        return [_to_candidate(c) for c in found.values()]

    async def _unique_slug(self, base: str, manufacturer: str | None) -> str:
        options = [slugify(base)]
        if manufacturer:
            options.append(slugify(f"{base}-{manufacturer}"))
        for opt in options:
            exists = (await self.s.execute(select(Component.id).where(Component.slug == opt))).first()
            if exists is None:
                return opt
        n = 2
        while True:
            opt = f"{options[-1]}-{n}"
            if (await self.s.execute(select(Component.id).where(Component.slug == opt))).first() is None:
                return opt
            n += 1

    async def create(self, c: NewComponent) -> uuid.UUID:
        mfr = normalize_manufacturer(c.manufacturer) or None
        category, sub = categorize(c.title, c.category_hint)
        # Race-safe: unique (mpn_norm, manufacturer_norm) → reuse the row another worker created.
        stmt = (
            insert(Component)
            .values(
                slug=await self._unique_slug(c.mpn, mfr),
                mpn=c.mpn,
                mpn_norm=mpn_key(c.mpn),
                manufacturer=mfr,
                manufacturer_norm=manufacturer_key(mfr),
                gtin=c.gtin,
                category=category,
                subcategory=sub,
                title=c.title,
                short_desc=(c.short_desc or None),
                specs=c.specs,
                specs_norm=c.specs_norm,
                package=c.package,
                datasheet_url=c.datasheet_url,
                datasheet_host=urlsplit(c.datasheet_url).hostname if c.datasheet_url else None,
                embedding=c.embedding,
            )
            .on_conflict_do_nothing()
            .returning(Component.id)
        )
        new_id = (await self.s.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            new_id = (
                await self.s.execute(
                    select(Component.id).where(
                        Component.mpn_norm == mpn_key(c.mpn),
                        Component.manufacturer_norm == manufacturer_key(mfr),
                        Component.status == "active",
                    )
                )
            ).scalar_one()
        if c.datasheet_url:
            await self.s.execute(
                insert(Datasheet)
                .values(
                    component_id=new_id,
                    url=c.datasheet_url,
                    host=urlsplit(c.datasheet_url).hostname or "",
                    is_primary=True,
                )
                .on_conflict_do_nothing()
            )
        return new_id

    async def attach(
        self, listing_id: uuid.UUID, component_id: uuid.UUID, confidence: float, method: str
    ) -> None:
        await self.s.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(component_id=component_id, match_confidence=confidence, match_method=method)
        )

    async def review(self, listing_id: uuid.UUID, decision: Decision, payload: dict[str, Any]) -> None:
        await self.s.execute(
            insert(ReviewItem)
            .values(kind="match", ref_id=str(listing_id), reason=decision.reason, payload=payload)
            .on_conflict_do_nothing()
        )

    async def audit(
        self,
        action: str,
        *,
        listing_id: uuid.UUID | None,
        from_component: uuid.UUID | None,
        to_component: uuid.UUID | None,
        confidence: float | None,
        method: str | None,
        actor: str,
        details: dict[str, Any],
    ) -> None:
        await write_audit(
            self.s,
            action,
            listing_id=listing_id,
            from_component=from_component,
            to_component=to_component,
            confidence=confidence,
            method=method,
            actor=actor,
            details=details,
        )
