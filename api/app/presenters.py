"""Turns domain objects (RankedOffer, Component, ...) into API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from api.app import repository as repo
from api.app.schemas import Money, OfferOut, OffersOut, SourceRef
from common.models import Component
from crawler.normalizer.currency import from_minor
from price.fx import FxTable
from price.geo import UserGeo
from price.ranker import RankedOffer, RankRequest, SortMode, rank_offers
from price.repository import fetch_active_offers, fetch_ship_quotes

DISPLAY_CURRENCIES = ("BDT", "USD", "EUR")


def money_from_micros(fx: FxTable, micros: int, currency: str) -> Money:
    minor = fx.from_usd_micros(micros, currency)
    return Money(amount=from_minor(minor, currency), currency=currency, usd_minor=round(micros / 10_000))


def freshness_label(observed_at: datetime, now: datetime) -> str:
    age_h = (now - observed_at).total_seconds() / 3600
    if age_h < 6:
        return "fresh"
    if age_h < 48:
        return "recent"
    return "stale"


async def ranked_offers(
    s: AsyncSession, comp: Component, geo: UserGeo, fx: FxTable, now: datetime, *,
    mode: SortMode, quantity: int, local_only: bool, in_stock_only: bool,
) -> list[RankedOffer]:
    offers = await fetch_active_offers(s, comp.id)
    quotes = await fetch_ship_quotes(s, list({o.source_id for o in offers}), geo.country)
    req = RankRequest(geo=geo, quantity=quantity, mode=mode, local_only=local_only, in_stock_only=in_stock_only)
    return rank_offers(offers, req, fx, now, quotes)


async def offers_out(
    s: AsyncSession, comp: Component, ranked: list[RankedOffer], geo: UserGeo, fx: FxTable, now: datetime, *,
    mode: SortMode, quantity: int, currency: str, local_only: bool, limit: int | None = None,
) -> OffersOut:
    chosen = ranked[:limit] if limit else ranked
    sources = await repo.sources_by_ids(s, list({r.offer.source_id for r in chosen}))
    titles = await repo.listing_titles(s, [r.offer.listing_id for r in chosen])
    out: list[OfferOut] = []
    for r in chosen:
        src = sources[r.offer.source_id]
        title, condition, stock_qty = titles.get(r.offer.listing_id, (comp.title, "new", None))
        out.append(
            OfferOut(
                listing_id=r.offer.listing_id,
                source=SourceRef(name=src.name, display_name=src.display_name, domain=src.domain,
                                 trust_score=float(src.trust_score)),
                url=r.offer.url,
                go_url=f"/go/{r.offer.listing_id}",
                sponsored=bool(src.affiliate_template),
                title=title,
                condition=condition,
                in_stock=r.offer.in_stock,
                stock_qty=stock_qty,
                moq=r.offer.moq,
                quantity=r.quantity,
                unit_price=money_from_micros(fx, r.unit_usd_micros, currency),
                landed_total=money_from_micros(fx, r.landed_usd_micros, currency),
                landed_per_unit=money_from_micros(fx, r.unit_landed_usd_micros, currency),
                shipping=money_from_micros(fx, r.shipping_usd_micros, currency),
                duty_estimate=money_from_micros(fx, r.duty_usd_micros, currency),
                eta_days=r.eta_days,
                distance_km=round(r.distance_km, 1) if r.distance_km is not None else None,
                ships_from=r.offer.ships_from,
                observed_at=r.offer.observed_at,
                freshness=freshness_label(r.offer.observed_at, now),  # type: ignore[arg-type]
                score=r.score,
            )
        )
    return OffersOut(
        component_slug=comp.slug, mode=mode.value, quantity=quantity, currency=currency, country=geo.country,
        city=geo.city, local_only=local_only, offers=out, total=len(ranked), fx_day=fx.day,
    )


def price_range(ranked: list[RankedOffer], fx: FxTable, currency: str) -> tuple[Money | None, Money | None]:
    vals = [r.unit_landed_usd_micros for r in ranked if r.offer.in_stock is not False]
    if not vals:
        return None, None
    return money_from_micros(fx, min(vals), currency), money_from_micros(fx, max(vals), currency)


def default_currency(geo: UserGeo) -> str:
    return "BDT" if geo.country == "BD" else ("EUR" if geo.country in {"DE", "FR", "NL", "IT", "ES", "IE"} else "USD")


def build_faq(comp: Component, low: Money | None, offer_count: int, has_datasheet: bool, queries: list[str]) -> list[tuple[str, str]]:
    """FAQ from facts we hold + real queries (§10.4). Answers only state stored facts."""
    faq: list[tuple[str, str]] = []
    if low is not None:
        faq.append((
            f"What is the price of {comp.mpn}?",
            f"The lowest landed price we currently see for {comp.mpn} is {low.currency} {low.amount:,.2f} per unit "
            f"across {offer_count} offer{'s' if offer_count != 1 else ''}, including shipping and estimated import duty.",
        ))
    if comp.package:
        faq.append((f"What package does {comp.mpn} come in?", f"{comp.mpn} is listed in a {comp.package} package."))
    if has_datasheet:
        faq.append((
            f"Where can I find the {comp.mpn} datasheet?",
            f"The datasheet link on this page points to the original document hosted by its publisher.",
        ))
    for q in queries[:2]:
        if "bangladesh" in q or " bd" in f" {q}" or "dhaka" in q:
            faq.append((
                f"Can I buy {comp.mpn} in Bangladesh?",
                "Use the 'Ships to Bangladesh' filter on the price table to see shops that deliver locally.",
            ))
            break
    return faq


def decimal_target_to_minor(target: Decimal, currency: str) -> int:
    from crawler.normalizer.currency import to_minor

    return to_minor(target, currency)


def as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
