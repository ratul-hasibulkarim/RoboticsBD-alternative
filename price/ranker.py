"""§7.1 — "lowest price from closest distance", ranked by total landed cost.

All money arithmetic happens in one currency (spec v1.1 §0 row 12): integer micro-USD
(1e-6 USD), fine enough that ৳ → USD → ৳ round-trips exactly at paisa resolution.
`*_usd_minor` properties give cents for storage/APIs; display converts back with FxTable.
Inputs are plain dataclasses so the ranker is pure and the
golden test (P2) needs no database.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from price.duty import estimate_duty_usd_micros
from price.fx import FxTable
from price.geo import UserGeo, haversine_km

W_COST, W_SPEED, W_PROXIMITY, W_TRUST, W_FRESH = 0.45, 0.25, 0.15, 0.10, 0.05
FRESHNESS_HALF = 0.3  # value at 30 days
FRESHNESS_DAYS = 30.0
OUT_OF_STOCK_FACTOR = 0.5
UNKNOWN_PROXIMITY = 0.3
SPEED_WEEK_DAYS = 7.0


class SortMode(enum.StrEnum):
    BEST = "best"
    CHEAPEST = "cheapest"
    FASTEST = "fastest"


@dataclass(frozen=True)
class PriceBreakMinor:
    qty: int
    price_minor: int


@dataclass(frozen=True)
class ShipQuote:
    cost_minor: int
    currency: str
    eta_days_min: int
    eta_days_max: int


@dataclass(frozen=True)
class Offer:
    listing_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    url: str
    currency: str
    price_minor: int  # unit price at qty 1 (or MOQ)
    observed_at: datetime
    price_breaks: tuple[PriceBreakMinor, ...] = ()
    moq: int = 1
    shipping_minor: int | None = None  # per-order shipping from the listing itself, if stated
    ships_from: str | None = None
    ships_to: tuple[str, ...] = ()
    warehouse_lat: float | None = None
    warehouse_lon: float | None = None
    trust_score: float = 0.5
    in_stock: bool | None = None
    stale_after_hours: int | None = None
    category: str | None = None


@dataclass(frozen=True)
class RankedOffer:
    offer: Offer
    quantity: int  # units actually bought (≥ MOQ)
    unit_usd_micros: int
    goods_usd_micros: int
    shipping_usd_micros: int
    duty_usd_micros: int
    landed_usd_micros: int
    eta_days: float
    distance_km: float | None
    freshness: float
    score: float
    score_parts: dict[str, float] = field(default_factory=dict)

    @property
    def landed_usd_minor(self) -> int:
        return round(self.landed_usd_micros / 10_000)

    @property
    def unit_landed_usd_micros(self) -> int:
        return round(self.landed_usd_micros / self.quantity)


@dataclass(frozen=True)
class RankRequest:
    geo: UserGeo
    quantity: int = 1
    mode: SortMode = SortMode.BEST
    local_only: bool = False
    in_stock_only: bool = False


def freshness(observed_at: datetime, now: datetime) -> float:
    """1.0 now, 0.3 at 30 days (P3), exponential in between and beyond."""
    age_days = max(0.0, (now - observed_at).total_seconds() / 86400)
    return float(FRESHNESS_HALF ** (age_days / FRESHNESS_DAYS))


def unit_price_minor(offer: Offer, quantity: int) -> tuple[int, int]:
    """Return (units bought, unit price in offer currency minor units) for a requested quantity."""
    qty = max(quantity, offer.moq, 1)
    breaks = sorted(offer.price_breaks, key=lambda b: b.qty)
    if breaks and breaks[0].qty > qty:
        qty = breaks[0].qty
    unit = offer.price_minor
    for b in breaks:
        if b.qty <= qty:
            unit = b.price_minor
    return qty, unit


def default_eta(offer: Offer, geo: UserGeo) -> tuple[int, int]:
    if offer.ships_from and offer.ships_from == geo.country:
        if offer.warehouse_lat is not None and geo.lat is not None and offer.warehouse_lon is not None and geo.lon is not None:
            if haversine_km(offer.warehouse_lat, offer.warehouse_lon, geo.lat, geo.lon) < 30:
                return 1, 2  # same city
        return 2, 4
    return 7, 21


def ships_to_user(offer: Offer, geo: UserGeo) -> bool:
    return "*" in offer.ships_to or geo.country in offer.ships_to


def rank_offers(
    offers: list[Offer],
    req: RankRequest,
    fx: FxTable,
    now: datetime,
    ship_quotes: dict[tuple[uuid.UUID, str], ShipQuote] | None = None,
) -> list[RankedOffer]:
    """Filter, price and sort offers. `ship_quotes` is keyed by (source_id, to_country)."""
    ship_quotes = ship_quotes or {}
    priced: list[RankedOffer] = []
    for o in offers:
        if not ships_to_user(o, req.geo):
            continue
        if req.local_only and o.ships_from != req.geo.country:
            continue
        if req.in_stock_only and o.in_stock is False:
            continue
        if o.stale_after_hours is not None and (now - o.observed_at).total_seconds() > o.stale_after_hours * 3600:
            continue  # too old to show (source cache TTL)

        qty, unit = unit_price_minor(o, req.quantity)
        unit_usd = fx.to_usd_micros(unit, o.currency)
        goods_usd = unit_usd * qty

        quote = ship_quotes.get((o.source_id, req.geo.country))
        if quote is not None:
            ship_usd = fx.to_usd_micros(quote.cost_minor, quote.currency)
            eta = (quote.eta_days_min + quote.eta_days_max) / 2
        else:
            ship_usd = fx.to_usd_micros(o.shipping_minor, o.currency) if o.shipping_minor else 0
            lo, hi = default_eta(o, req.geo)
            eta = (lo + hi) / 2

        duty = estimate_duty_usd_micros(o.ships_from, req.geo.country, goods_usd + ship_usd, o.category)
        landed = goods_usd + ship_usd + duty

        distance = None
        if None not in (o.warehouse_lat, o.warehouse_lon, req.geo.lat, req.geo.lon):
            distance = haversine_km(o.warehouse_lat, o.warehouse_lon, req.geo.lat, req.geo.lon)  # type: ignore[arg-type]

        priced.append(
            RankedOffer(
                offer=o,
                quantity=qty,
                unit_usd_micros=unit_usd,
                goods_usd_micros=goods_usd,
                shipping_usd_micros=ship_usd,
                duty_usd_micros=duty,
                landed_usd_micros=landed,
                eta_days=eta,
                distance_km=distance,
                freshness=freshness(o.observed_at, now),
                score=0.0,
            )
        )
    if not priced:
        return []

    # Compare per requested unit so offers forced to a larger MOQ are not unfairly favoured/penalised.
    def per_unit(r: RankedOffer) -> float:
        return r.landed_usd_micros / r.quantity

    min_cost = min(per_unit(r) for r in priced)
    min_eta = min(r.eta_days for r in priced)
    scored: list[RankedOffer] = []
    for r in priced:
        cost_s = (min_cost / per_unit(r)) if per_unit(r) > 0 else 1.0
        # each extra week of delivery halves the speed score relative to the fastest offer
        speed_s = 1.0 / (1.0 + (r.eta_days - min_eta) / SPEED_WEEK_DAYS)
        prox_s = UNKNOWN_PROXIMITY if r.distance_km is None else 1.0 / (1.0 + r.distance_km / 500.0)
        trust = float(r.offer.trust_score)
        score = W_COST * cost_s + W_SPEED * speed_s + W_PROXIMITY * prox_s + W_TRUST * trust + W_FRESH * r.freshness
        if r.offer.in_stock is False:
            score *= OUT_OF_STOCK_FACTOR
        parts = {"cost": cost_s, "speed": speed_s, "proximity": prox_s, "trust": trust, "freshness": r.freshness}
        scored.append(
            RankedOffer(**{**r.__dict__, "score": round(score, 6), "score_parts": parts})
        )

    def stock_key(r: RankedOffer) -> int:
        return 1 if r.offer.in_stock is False else 0

    if req.mode is SortMode.CHEAPEST:
        scored.sort(key=lambda r: (stock_key(r), per_unit(r), r.eta_days))
    elif req.mode is SortMode.FASTEST:
        scored.sort(key=lambda r: (stock_key(r), r.eta_days, per_unit(r)))
    else:
        scored.sort(key=lambda r: (-r.score, per_unit(r)))
    return scored


def landed_in(r: RankedOffer, fx: FxTable, currency: str, *, per_unit: bool = False) -> Decimal:
    from crawler.normalizer.currency import from_minor

    micros = r.unit_landed_usd_micros if per_unit else r.landed_usd_micros
    return from_minor(fx.from_usd_micros(micros, currency), currency)
