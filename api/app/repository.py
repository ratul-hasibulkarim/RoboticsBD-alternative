"""Repository functions for the API. Routers never contain SQL (spec §15)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import (
    Component,
    ComponentImage,
    ComponentViewsDaily,
    Datasheet,
    Image,
    Listing,
    PriceCurrent,
    PriceDaily,
    Query,
    Source,
    UseCase,
)
from common.timeutil import utcnow
from crawler.normalizer.units import spec_overlap


def manufacturer_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def component_by_slug(s: AsyncSession, slug: str) -> Component | None:
    return (await s.execute(select(Component).where(Component.slug == slug))).scalar_one_or_none()


async def component_by_id(s: AsyncSession, cid: uuid.UUID) -> Component | None:
    return await s.get(Component, cid)


async def images_for(s: AsyncSession, cid: uuid.UUID) -> list[Image]:
    rows = (
        await s.execute(
            select(Image)
            .join(ComponentImage, ComponentImage.image_id == Image.id)
            .where(ComponentImage.component_id == cid)
            .order_by(ComponentImage.position)
        )
    ).scalars()
    images = list(rows)
    if images:
        return images
    # Fall back to listing images (hotlinked, attributed to their source).
    fallback = (
        await s.execute(
            select(Listing.image_url, Source.display_name)
            .join(Source, Source.id == Listing.source_id)
            .where(Listing.component_id == cid, Listing.image_url.is_not(None), Listing.active.is_(True))
            .limit(6)
        )
    ).all()
    return [
        Image(source_url=url, attribution=f"Image: {name}", license="source-hosted", width=None, height=None)
        for url, name in fallback
    ]


async def datasheets_for(s: AsyncSession, cid: uuid.UUID) -> list[Datasheet]:
    return list(
        (
            await s.execute(
                select(Datasheet).where(Datasheet.component_id == cid).order_by(Datasheet.is_primary.desc(), Datasheet.checked_at.desc())
            )
        ).scalars()
    )


async def use_cases_for(s: AsyncSession, cid: uuid.UUID, limit: int = 12) -> list[UseCase]:
    return list(
        (
            await s.execute(
                select(UseCase)
                .where(UseCase.component_id == cid)
                .order_by(UseCase.upvotes.desc(), UseCase.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )


def _card_query() -> Any:
    stats = (
        select(
            Listing.component_id.label("cid"),
            func.min(PriceCurrent.landed_usd_minor).filter(Listing.in_stock.is_not(False)).label("lowest"),
            func.count(PriceCurrent.listing_id).label("offers"),
        )
        .join(PriceCurrent, PriceCurrent.listing_id == Listing.id)
        .where(Listing.active.is_(True))
        .group_by(Listing.component_id)
        .subquery()
    )
    q = (
        select(Component, stats.c.lowest, stats.c.offers, Image.source_url)
        .outerjoin(stats, stats.c.cid == Component.id)
        .outerjoin(Image, Image.id == Component.primary_image)
        .where(Component.status == "active")
    )
    return q, stats


def card_dict(row: Any) -> dict[str, Any]:
    c, lowest, offers, image_url = row
    return {
        "slug": c.slug,
        "mpn": c.mpn,
        "title": c.title,
        "manufacturer": c.manufacturer,
        "category": c.category,
        "subcategory": c.subcategory,
        "package": c.package,
        "image_url": image_url,
        "lowest_price_usd_minor": int(lowest) if lowest is not None else None,
        "offer_count": int(offers or 0),
    }


async def cards_by_ids(s: AsyncSession, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not ids:
        return []
    q, _ = _card_query()
    by_id = {r[0].id: card_dict(r) for r in (await s.execute(q.where(Component.id.in_(ids)))).all()}
    return [by_id[i] for i in ids if i in by_id]


async def alternatives(s: AsyncSession, comp: Component, limit: int = 4) -> list[dict[str, Any]]:
    """Pin/spec-similar substitutes: same category, nearest embeddings, spec overlap ≥ 0.6, MPN differs."""
    if comp.embedding is None:
        return []
    q, _ = _card_query()
    rows = (
        await s.execute(
            q.where(Component.id != comp.id, Component.category == comp.category, Component.embedding.is_not(None))
            .order_by(Component.embedding.cosine_distance(list(comp.embedding)))
            .limit(limit * 5)
        )
    ).all()
    out = []
    for r in rows:
        other: Component = r[0]
        if spec_overlap(comp.specs_norm or {}, other.specs_norm or {}) >= 0.6:
            out.append(card_dict(r))
        if len(out) >= limit:
            break
    return out


async def related(s: AsyncSession, comp: Component, limit: int = 6) -> list[dict[str, Any]]:
    """Internal linking (§10.3): same subcategory/manufacturer, most popular first."""
    q, _ = _card_query()
    conds = [Component.id != comp.id]
    peer = or_(
        and_(Component.category == comp.category, Component.subcategory == comp.subcategory)
        if comp.subcategory
        else Component.category == comp.category,
        Component.manufacturer_norm == comp.manufacturer_norm if comp.manufacturer_norm else Component.id == comp.id,
    )
    rows = (await s.execute(q.where(*conds, peer).order_by(Component.popularity.desc(), Component.slug).limit(limit))).all()
    return [card_dict(r) for r in rows]


async def history(s: AsyncSession, cid: uuid.UUID, days: int = 90) -> list[tuple[date, int]]:
    since = utcnow().date() - timedelta(days=days)
    rows = (
        await s.execute(
            select(PriceDaily.day, func.min(PriceDaily.usd_min_minor))
            .join(Listing, Listing.id == PriceDaily.listing_id)
            .where(Listing.component_id == cid, PriceDaily.day >= since)
            .group_by(PriceDaily.day)
            .order_by(PriceDaily.day)
        )
    ).all()
    return [(d, int(v)) for d, v in rows]


async def listing_with_source(s: AsyncSession, listing_id: uuid.UUID) -> tuple[Listing, Source] | None:
    row = (
        await s.execute(select(Listing, Source).join(Source, Source.id == Listing.source_id).where(Listing.id == listing_id))
    ).first()
    return (row[0], row[1]) if row else None


async def listing_titles(s: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str, int | None]]:
    if not ids:
        return {}
    rows = (await s.execute(select(Listing.id, Listing.raw_title, Listing.condition, Listing.stock_qty).where(Listing.id.in_(ids)))).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


async def sources_by_ids(s: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Source]:
    if not ids:
        return {}
    return {src.id: src for src in (await s.execute(select(Source).where(Source.id.in_(ids)))).scalars()}


async def record_view(s: AsyncSession, cid: uuid.UUID) -> None:
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(ComponentViewsDaily).values(day=utcnow().date(), component_id=cid, views=1)
    await s.execute(stmt.on_conflict_do_update(index_elements=["component_id", "day"], set_={"views": ComponentViewsDaily.views + 1}))


async def record_click(s: AsyncSession, listing_id: uuid.UUID, country: str | None, session_hash: str | None) -> None:
    s.add(Query(time=utcnow(), query_norm="__click__", clicked_listing=listing_id, user_country=country, session_hash=session_hash))
    await s.flush()


async def categories(s: AsyncSession) -> list[tuple[str, int]]:
    rows = (
        await s.execute(
            select(Component.category, func.count()).where(Component.status == "active").group_by(Component.category).order_by(func.count().desc())
        )
    ).all()
    return [(c, int(n)) for c, n in rows]


async def manufacturers(s: AsyncSession, limit: int = 500) -> list[tuple[str, int]]:
    rows = (
        await s.execute(
            select(Component.manufacturer, func.count())
            .where(Component.status == "active", Component.manufacturer.is_not(None))
            .group_by(Component.manufacturer)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    return [(m, int(n)) for m, n in rows]


async def manufacturer_by_slug(s: AsyncSession, slug: str) -> str | None:
    for name, _ in await manufacturers(s, limit=5000):
        if manufacturer_slug(name) == slug:
            return name
    return None


async def components_page(
    s: AsyncSession, *, category: str | None = None, manufacturer: str | None = None, page: int = 1, per_page: int = 24,
    ships_to_bd: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    q, _ = _card_query()
    if category:
        q = q.where(Component.category == category)
    if manufacturer:
        q = q.where(Component.manufacturer == manufacturer)
    if ships_to_bd:
        bd_ids = (
            select(Listing.component_id)
            .where(Listing.active.is_(True), or_(Listing.ships_to.any("BD"), Listing.ships_to.any("*")))
            .scalar_subquery()
        )
        q = q.where(Component.id.in_(bd_ids))
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await s.execute(q.order_by(Component.popularity.desc(), Component.slug).limit(per_page).offset((page - 1) * per_page))).all()
    return [card_dict(r) for r in rows], int(total)


async def trending(s: AsyncSession, limit: int = 12) -> list[dict[str, Any]]:
    since = utcnow().date() - timedelta(days=7)
    views = (
        select(ComponentViewsDaily.component_id, func.sum(ComponentViewsDaily.views).label("v"))
        .where(ComponentViewsDaily.day >= since)
        .group_by(ComponentViewsDaily.component_id)
        .subquery()
    )
    q, _ = _card_query()
    rows = (
        await s.execute(
            q.outerjoin(views, views.c.component_id == Component.id)
            .order_by(func.coalesce(views.c.v, 0).desc(), Component.popularity.desc(), Component.slug)
            .limit(limit)
        )
    ).all()
    return [card_dict(r) for r in rows]


async def sitemap_entries(s: AsyncSession, page: int, per_page: int = 45_000) -> list[tuple[str, datetime, str | None]]:
    rows = (
        await s.execute(
            select(Component.slug, Component.updated_at, Image.source_url)
            .outerjoin(Image, Image.id == Component.primary_image)
            .where(Component.status == "active")
            .order_by(Component.slug)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def sitemap_count(s: AsyncSession) -> int:
    return int((await s.execute(select(func.count()).select_from(Component).where(Component.status == "active"))).scalar_one())


async def top_queries_for(s: AsyncSession, comp: Component, limit: int = 5) -> list[str]:
    """Real search queries that led to this part (§10.4 FAQ seed)."""
    key = comp.mpn.lower()
    rows = (
        await s.execute(
            select(Query.query_norm, func.count())
            .where(Query.query_norm.like(f"%{key}%"), Query.query_norm != key, Query.time >= utcnow() - timedelta(days=90))
            .group_by(Query.query_norm)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    return [r[0] for r in rows]


async def merged_target_slug(s: AsyncSession, comp: Component) -> str | None:
    seen = set()
    cur = comp
    while cur.status == "merged" and cur.merged_into and cur.merged_into not in seen:
        seen.add(cur.merged_into)
        nxt = await s.get(Component, cur.merged_into)
        if nxt is None:
            return None
        cur = nxt
    return cur.slug if cur.status == "active" else None
