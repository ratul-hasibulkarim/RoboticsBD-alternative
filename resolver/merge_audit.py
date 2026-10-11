"""Merge / split operations on components. Every change writes a merge_audit row (test R3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Listing, MergeAudit, ReviewItem
from crawler.normalizer.mpn import mpn_key
from resolver.categorize import slugify
from resolver.matcher import MERGE_THRESHOLD, Candidate, should_merge


class MergeRefusedError(ValueError):
    pass


async def write_audit(
    s: AsyncSession,
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
    s.add(
        MergeAudit(
            action=action,
            listing_id=listing_id,
            from_component=from_component,
            to_component=to_component,
            confidence=confidence,
            method=method,
            actor=actor,
            details=details,
        )
    )
    await s.flush()


def _cand(c: Component) -> Candidate:
    return Candidate(id=c.id, mpn=c.mpn, manufacturer=c.manufacturer, gtin=c.gtin, package=c.package)


async def merge_components(
    s: AsyncSession, keep_id: uuid.UUID, drop_id: uuid.UUID, *, actor: str, force: bool = False
) -> int:
    """Move every listing from `drop` to `keep`; `drop` becomes status='merged' (→ 301 redirect).

    Automatic merges (force=False) require should_merge() ≥ MERGE_THRESHOLD. Admins may force.
    Returns the number of listings moved.
    """
    if keep_id == drop_id:
        raise MergeRefusedError("cannot merge a component into itself")
    keep = await s.get(Component, keep_id)
    drop = await s.get(Component, drop_id)
    if keep is None or drop is None or keep.status != "active" or drop.status != "active":
        raise MergeRefusedError("both components must exist and be active")
    ok, confidence, method = should_merge(_cand(keep), _cand(drop))
    if not force and (not ok or confidence < MERGE_THRESHOLD):
        raise MergeRefusedError(f"confidence {confidence:.2f} below {MERGE_THRESHOLD}")
    if not ok:
        confidence, method = 1.0, "manual"

    listing_ids = list(
        (await s.execute(select(Listing.id).where(Listing.component_id == drop_id))).scalars()
    )
    await s.execute(
        update(Listing)
        .where(Listing.component_id == drop_id)
        .values(component_id=keep_id, match_method="manual" if force else method)
    )
    await s.execute(
        update(Component).where(Component.id == drop_id).values(status="merged", merged_into=keep_id)
    )
    await write_audit(
        s,
        "merge",
        listing_id=None,
        from_component=drop_id,
        to_component=keep_id,
        confidence=confidence,
        method=method,
        actor=actor,
        details={"moved_listings": [str(i) for i in listing_ids], "forced": force},
    )
    for lid in listing_ids:
        await write_audit(
            s,
            "attach",
            listing_id=lid,
            from_component=drop_id,
            to_component=keep_id,
            confidence=confidence,
            method=method,
            actor=actor,
            details={"via": "merge"},
        )
    return len(listing_ids)


async def split_component(
    s: AsyncSession,
    component_id: uuid.UUID,
    listing_ids: list[uuid.UUID],
    *,
    new_mpn: str,
    new_manufacturer: str | None,
    actor: str,
) -> uuid.UUID:
    """Admin split: move `listing_ids` from `component_id` onto a new component."""
    src = await s.get(Component, component_id)
    if src is None:
        raise MergeRefusedError("component not found")
    owned = set(
        (
            await s.execute(
                select(Listing.id).where(Listing.component_id == component_id, Listing.id.in_(listing_ids))
            )
        ).scalars()
    )
    missing = set(listing_ids) - owned
    if missing:
        raise MergeRefusedError(f"listings not on component: {sorted(map(str, missing))}")

    from crawler.normalizer.mpn import manufacturer_key, normalize_manufacturer, normalize_mpn

    mfr = normalize_manufacturer(new_manufacturer) or None
    base_slug = slugify(new_mpn)
    slug = base_slug
    n = 2
    while (await s.execute(select(Component.id).where(Component.slug == slug))).first() is not None:
        slug = f"{base_slug}-{n}"
        n += 1
    new = Component(
        slug=slug,
        mpn=normalize_mpn(new_mpn),
        mpn_norm=mpn_key(new_mpn),
        manufacturer=mfr,
        manufacturer_norm=manufacturer_key(mfr),
        category=src.category,
        subcategory=src.subcategory,
        title=normalize_mpn(new_mpn) if not mfr else f"{mfr} {normalize_mpn(new_mpn)}",
        specs={},
        specs_norm={},
    )
    s.add(new)
    await s.flush()
    await s.execute(
        update(Listing).where(Listing.id.in_(listing_ids)).values(component_id=new.id, match_method="manual")
    )
    await write_audit(
        s,
        "split",
        listing_id=None,
        from_component=component_id,
        to_component=new.id,
        confidence=1.0,
        method="manual",
        actor=actor,
        details={"moved_listings": [str(i) for i in listing_ids]},
    )
    for lid in listing_ids:
        await write_audit(
            s,
            "attach",
            listing_id=lid,
            from_component=component_id,
            to_component=new.id,
            confidence=1.0,
            method="manual",
            actor=actor,
            details={"via": "split"},
        )
    return new.id


async def resolve_review_item(
    s: AsyncSession, review_id: int, *, component_id: uuid.UUID | None, actor: str
) -> None:
    """Admin decision on a 'match' review item: attach to component_id, or reject (None)."""
    item = await s.get(ReviewItem, review_id)
    if item is None or item.kind != "match" or item.status != "open":
        raise MergeRefusedError("review item not open")
    from common.timeutil import utcnow

    listing_id = uuid.UUID(item.ref_id)
    if component_id is not None:
        await s.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(component_id=component_id, match_confidence=1.0, match_method="manual")
        )
        await write_audit(
            s,
            "attach",
            listing_id=listing_id,
            from_component=None,
            to_component=component_id,
            confidence=1.0,
            method="manual",
            actor=actor,
            details={"review_id": review_id},
        )
    item.status = "resolved" if component_id else "rejected"
    item.resolved_at = utcnow()
    item.resolved_by = actor
    await s.flush()
