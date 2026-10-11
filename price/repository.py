"""Repository functions: load offers and shipping quotes for the ranker."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Listing, PriceCurrent, ShipEstimate, Source
from price.ranker import Offer, PriceBreakMinor, ShipQuote


async def fetch_active_offers(s: AsyncSession, component_id: uuid.UUID) -> list[Offer]:
    rows = (
        await s.execute(
            select(Listing, PriceCurrent, Source, Component.category)
            .join(PriceCurrent, PriceCurrent.listing_id == Listing.id)
            .join(Source, Source.id == Listing.source_id)
            .join(Component, Component.id == Listing.component_id)
            .where(
                Listing.component_id == component_id,
                Listing.active.is_(True),
                Source.active.is_(True),
                Source.legal_review_status != "blocked",
            )
        )
    ).all()
    offers: list[Offer] = []
    for listing, pc, src, category in rows:
        offers.append(
            Offer(
                listing_id=listing.id,
                source_id=src.id,
                source_name=src.display_name,
                url=listing.url,
                currency=pc.currency,
                price_minor=pc.price_minor,
                observed_at=pc.observed_at,
                price_breaks=tuple(
                    PriceBreakMinor(int(b["qty"]), int(b["price_minor"])) for b in (pc.price_breaks or [])
                ),
                moq=pc.moq,
                shipping_minor=pc.shipping_minor,
                ships_from=listing.ships_from or src.warehouse_country or src.country,
                ships_to=tuple(listing.ships_to or src.ships_to or []),
                warehouse_lat=src.warehouse_lat,
                warehouse_lon=src.warehouse_lon,
                trust_score=float(src.trust_score),
                in_stock=listing.in_stock,
                stale_after_hours=src.cache_ttl_hours * 3 if src.cache_ttl_hours else None,
                category=category,
            )
        )
    return offers


async def fetch_ship_quotes(
    s: AsyncSession, source_ids: list[uuid.UUID], to_country: str
) -> dict[tuple[uuid.UUID, str], ShipQuote]:
    if not source_ids:
        return {}
    rows = (
        await s.execute(
            select(ShipEstimate)
            .where(ShipEstimate.source_id.in_(source_ids), ShipEstimate.to_country == to_country)
            .order_by(ShipEstimate.cost_minor)
        )
    ).scalars()
    out: dict[tuple[uuid.UUID, str], ShipQuote] = {}
    for r in rows:
        out.setdefault((r.source_id, r.to_country), ShipQuote(r.cost_minor, r.currency, r.eta_days_min, r.eta_days_max))
    return out
