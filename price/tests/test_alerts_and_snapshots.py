"""P4 (fires once per crossing) and snapshot/rollup/retention against Postgres."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Listing, PriceAlert, PriceCurrent, PriceDaily, PriceSnapshot, Source, User
from price.alerts import AlertMessage, Transition, evaluate_alerts, transition
from price.fx import FxTable
from price.snapshotter import Observation, apply_retention, record

T0 = datetime(2026, 10, 11, 8, 0, tzinfo=UTC)
FX = FxTable(day=T0.date(), per_usd={"BDT": Decimal("122")})


def test_transition_state_machine() -> None:
    assert transition(True, 100, 100) is Transition.FIRE
    assert transition(False, 90, 100) is Transition.NONE  # already fired, still below
    assert transition(False, 101, 100) is Transition.NONE  # inside 2 % hysteresis
    assert transition(False, 103, 100) is Transition.REARM
    assert transition(True, 150, 100) is Transition.NONE


class Outbox:
    def __init__(self) -> None:
        self.sent: list[AlertMessage] = []

    async def send(self, msg: AlertMessage) -> None:
        self.sent.append(msg)


async def _setup(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    src = Source(
        name="rbd",
        display_name="RoboticsBD",
        domain="r.test",
        type="crawl",
        base_url="https://r.test",
        legal_review_status="approved",
        country="BD",
        warehouse_country="BD",
        ships_to=["BD"],
        warehouse_lat=23.81,
        warehouse_lon=90.41,
        trust_score=0.8,
        cache_ttl_hours=48,
    )
    comp = Component(
        slug="esp32-wroom-32",
        mpn="ESP32-WROOM-32",
        mpn_norm="esp32wroom32",
        category="wireless",
        title="ESP32-WROOM-32",
    )
    db.add_all([src, comp])
    await db.flush()
    listing = Listing(
        source_id=src.id,
        url="https://r.test/esp32",
        url_hash="h1",
        raw_title="ESP32",
        component_id=comp.id,
        in_stock=True,
        ships_from="BD",
        ships_to=["BD"],
    )
    user = User(email="maker@example.com")
    db.add_all([listing, user])
    await db.flush()
    db.add(PriceAlert(user_id=user.id, component_id=comp.id, target_minor=50000, currency="BDT", ship_to="BD"))
    await db.flush()
    return listing.id, comp.id


@pytest.mark.db
async def test_p4_alert_fires_once_per_crossing(db: AsyncSession) -> None:
    lid, _ = await _setup(db)
    out = Outbox()
    prices = [Decimal("560"), Decimal("490"), Decimal("480"), Decimal("495"), Decimal("540"), Decimal("470")]
    for i, p in enumerate(prices):
        now = T0 + timedelta(minutes=15 * i)
        await record(db, Observation(lid, "BDT", p, now), FX)
        await evaluate_alerts(db, FX, now, out)
    # crossings: 560→490 (fire), 480/495 still below (no repeat), 540 re-arms, 470 fires again
    assert [m.price for m in out.sent] == [Decimal("490.00"), Decimal("470.00")]
    alert = (await db.execute(select(PriceAlert))).scalar_one()
    assert alert.armed is False and alert.last_fired_at == T0 + timedelta(minutes=75)


@pytest.mark.db
async def test_snapshots_current_and_daily_rollup(db: AsyncSession) -> None:
    lid, _ = await _setup(db)
    r1 = await record(db, Observation(lid, "BDT", Decimal("520"), T0), FX)
    r2 = await record(db, Observation(lid, "BDT", Decimal("520"), T0 + timedelta(hours=6)), FX)  # unchanged
    r3 = await record(db, Observation(lid, "BDT", Decimal("480"), T0 + timedelta(hours=12)), FX)
    assert (r1.changed, r2.changed, r3.changed) == (True, False, True)
    n = (await db.execute(select(func.count()).select_from(PriceSnapshot))).scalar()
    assert n == 2  # unchanged same-day observation is not duplicated
    cur = await db.get(PriceCurrent, lid)
    assert cur is not None and cur.price_minor == 48000 and cur.price_usd_minor == 393
    daily = (await db.execute(select(PriceDaily))).scalar_one()
    assert (daily.min_minor, daily.max_minor, daily.close_minor) == (48000, 52000, 48000)


@pytest.mark.db
async def test_retention(db: AsyncSession) -> None:
    lid, _ = await _setup(db)
    await record(db, Observation(lid, "BDT", Decimal("520"), T0 - timedelta(days=120)), FX)
    await record(db, Observation(lid, "BDT", Decimal("500"), T0), FX)
    raw, daily = await apply_retention(db, T0)
    assert raw == 1 and daily == 0
    assert (await db.execute(select(func.count()).select_from(PriceDaily))).scalar() == 2
