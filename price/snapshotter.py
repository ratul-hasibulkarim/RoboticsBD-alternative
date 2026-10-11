"""Writes price observations: price_snapshots (history), price_current (latest), price_daily (rollup).

Retention (§7.3): raw snapshots 90 days, daily rollup 5 years — `apply_retention`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import PriceCurrent, PriceDaily, PriceSnapshot
from crawler.normalizer.currency import to_minor
from price.fx import FxTable

RAW_RETENTION = timedelta(days=90)
DAILY_RETENTION = timedelta(days=5 * 365)


@dataclass(frozen=True)
class Observation:
    listing_id: uuid.UUID
    currency: str
    price: Decimal
    observed_at: datetime
    price_breaks: tuple[tuple[int, Decimal], ...] = ()
    moq: int = 1
    shipping: Decimal | None = None
    tax_included: bool | None = None


@dataclass(frozen=True)
class SnapshotResult:
    changed: bool
    price_minor: int
    price_usd_minor: int
    previous_usd_minor: int | None


def _breaks_json(obs: Observation) -> list[dict[str, int]]:
    return [{"qty": q, "price_minor": to_minor(p, obs.currency)} for q, p in sorted(obs.price_breaks)]


async def record(s: AsyncSession, obs: Observation, fx: FxTable) -> SnapshotResult:
    price_minor = to_minor(obs.price, obs.currency)
    shipping_minor = to_minor(obs.shipping, obs.currency) if obs.shipping is not None else None
    breaks = _breaks_json(obs)
    price_usd = fx.to_usd_minor(price_minor, obs.currency)
    landed_usd = price_usd + (fx.to_usd_minor(shipping_minor, obs.currency) if shipping_minor else 0)

    prev = await s.get(PriceCurrent, obs.listing_id)
    previous_usd = prev.landed_usd_minor if prev else None
    changed = (
        prev is None
        or prev.price_minor != price_minor
        or prev.currency != obs.currency
        or prev.shipping_minor != shipping_minor
        or prev.price_breaks != breaks
        or prev.moq != obs.moq
    )

    # History: one row per observation that changed, plus at least one per day (for charts).
    last_today = None
    if not changed:
        last_today = (
            await s.execute(
                select(func.max(PriceSnapshot.time)).where(
                    PriceSnapshot.listing_id == obs.listing_id,
                    PriceSnapshot.time >= obs.observed_at.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            )
        ).scalar()
    if changed or last_today is None:
        await s.execute(
            insert(PriceSnapshot).values(
                time=obs.observed_at,
                listing_id=obs.listing_id,
                currency=obs.currency,
                price_minor=price_minor,
                price_breaks=breaks,
                moq=obs.moq,
                shipping_minor=shipping_minor,
                tax_included=obs.tax_included,
                observed_at=obs.observed_at,
            )
        )

    values = {
        "currency": obs.currency,
        "price_minor": price_minor,
        "price_breaks": breaks,
        "moq": obs.moq,
        "shipping_minor": shipping_minor,
        "price_usd_minor": price_usd,
        "landed_usd_minor": landed_usd,
        "observed_at": obs.observed_at,
        "updated_at": obs.observed_at,
    }
    stmt = insert(PriceCurrent).values(listing_id=obs.listing_id, **values)
    await s.execute(stmt.on_conflict_do_update(index_elements=["listing_id"], set_=values))

    day = obs.observed_at.date()
    daily = insert(PriceDaily).values(
        day=day,
        listing_id=obs.listing_id,
        currency=obs.currency,
        min_minor=price_minor,
        max_minor=price_minor,
        close_minor=price_minor,
        usd_min_minor=price_usd,
    )
    await s.execute(
        daily.on_conflict_do_update(
            index_elements=["listing_id", "day"],
            set_={
                "min_minor": func.least(PriceDaily.min_minor, daily.excluded.min_minor),
                "max_minor": func.greatest(PriceDaily.max_minor, daily.excluded.max_minor),
                "close_minor": daily.excluded.close_minor,
                "usd_min_minor": func.least(PriceDaily.usd_min_minor, daily.excluded.usd_min_minor),
                "currency": daily.excluded.currency,
            },
        )
    )
    return SnapshotResult(changed, price_minor, price_usd, previous_usd)


async def apply_retention(s: AsyncSession, now: datetime) -> tuple[int, int]:
    raw = await s.execute(delete(PriceSnapshot).where(PriceSnapshot.time < now - RAW_RETENTION))
    daily = await s.execute(delete(PriceDaily).where(PriceDaily.day < (now - DAILY_RETENTION).date()))
    return int(raw.rowcount or 0), int(daily.rowcount or 0)  # type: ignore[attr-defined]
