"""P1 FX round-trip, P2 golden ranker, P3 freshness decay, plus ranker unit rules."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from price.duty import estimate_duty_usd_micros
from price.fx import FxTable
from price.geo import geo_from_headers, haversine_km, resolve_geo
from price.ranker import RankRequest, SortMode, freshness, rank_offers, unit_price_minor
from price.tests.golden_scenarios import FX, GEOS, NOW, QUOTES, SCENARIOS, offer

GOLDEN = json.loads((Path(__file__).parent / "golden_ranker.json").read_text())


@pytest.mark.parametrize("amount", [1, 99, 52000, 123456789, 7])
@pytest.mark.parametrize("cur", ["BDT", "EUR", "INR", "CNY"])
def test_p1_fx_round_trip_within_0_1_percent(amount: int, cur: str) -> None:
    usd = amount
    there = FX.from_usd_minor(usd, cur)
    back = FX.to_usd_minor(there, cur)
    # minor-unit rounding: allow 0.1 % or one minor unit for tiny amounts
    assert abs(back - usd) <= max(usd * 0.001, 1)


def test_micros_round_trip_is_exact_at_paisa() -> None:
    for paisa in (1000, 49000, 52000, 99, 1):
        assert FX.from_usd_micros(FX.to_usd_micros(paisa, "BDT"), "BDT") == paisa


def test_fx_bdt_specifics() -> None:
    fx = FxTable(day=NOW.date(), per_usd={"BDT": Decimal("122")})
    assert fx.to_usd_minor(52000, "BDT") == 426  # ৳520 → $4.26
    assert fx.from_usd_minor(100, "BDT") == 12200


def test_p2_golden_set_has_50_cases() -> None:
    assert len(GOLDEN) == 50
    assert {c["scenario"] for c in GOLDEN} == set(SCENARIOS)


@pytest.mark.parametrize("case", GOLDEN, ids=[f"{c['scenario']}-{c['geo']}" for c in GOLDEN])
def test_p2_golden_top3(case: dict[str, object]) -> None:
    qty, offers = SCENARIOS[str(case["scenario"])]
    geo = GEOS[str(case["geo"])]
    for mode in SortMode:
        ranked = rank_offers(offers, RankRequest(geo=geo, quantity=qty, mode=mode), FX, NOW, QUOTES)
        assert [r.offer.source_name for r in ranked[:3]] == case[mode.value], mode


def test_p3_freshness_decay() -> None:
    assert freshness(NOW, NOW) == 1.0
    assert freshness(NOW - timedelta(days=30), NOW) <= 0.3 + 1e-9
    assert freshness(NOW - timedelta(days=60), NOW) < freshness(NOW - timedelta(days=30), NOW)
    assert freshness(NOW - timedelta(hours=6), NOW) > 0.99


def test_price_breaks_and_moq() -> None:
    o = offer("LCSC", "USD", 280, breaks=((1, 280), (10, 250), (100, 210)), moq=1)
    assert unit_price_minor(o, 1) == (1, 280)
    assert unit_price_minor(o, 50) == (50, 250)
    assert unit_price_minor(o, 100) == (100, 210)
    moq = offer("LCSC", "USD", 5, moq=10)
    assert unit_price_minor(moq, 1) == (10, 5)


def test_cheapest_and_fastest_modes() -> None:
    _, offers = SCENARIOS["global_only"]
    geo = GEOS["dhaka"]
    cheapest = rank_offers(offers, RankRequest(geo=geo, mode=SortMode.CHEAPEST), FX, NOW, QUOTES)
    fastest = rank_offers(offers, RankRequest(geo=geo, mode=SortMode.FASTEST), FX, NOW, QUOTES)
    assert [r.landed_usd_micros for r in cheapest] == sorted(r.landed_usd_micros for r in cheapest)
    assert fastest[0].offer.source_name == "DigiKey"  # 3–5 days


def test_local_only_and_ships_to_filters() -> None:
    _, offers = SCENARIOS["esp32_qty1"]
    local = rank_offers(offers, RankRequest(geo=GEOS["dhaka"], local_only=True), FX, NOW, QUOTES)
    assert {r.offer.ships_from for r in local} == {"BD"}
    berlin = rank_offers(offers, RankRequest(geo=GEOS["berlin"]), FX, NOW, QUOTES)
    assert all(r.offer.ships_from != "BD" for r in berlin)


def test_currency_never_mixed() -> None:
    """Landed cost is goods + shipping + duty, all in USD minor units."""
    _, offers = SCENARIOS["india_shop"]
    ranked = rank_offers(offers, RankRequest(geo=GEOS["dhaka"]), FX, NOW, QUOTES)
    kolkata = next(r for r in ranked if r.offer.source_name == "Kolkata Parts")
    assert kolkata.goods_usd_micros == FX.to_usd_micros(15000, "INR")
    assert kolkata.shipping_usd_micros == FX.to_usd_micros(30000, "INR")
    assert kolkata.landed_usd_micros == kolkata.goods_usd_micros + kolkata.shipping_usd_micros + kolkata.duty_usd_micros


def test_stale_offers_hidden() -> None:
    o = offer("RoboticsBD", "BDT", 100, age_days=10)
    o2 = type(o)(**{**o.__dict__, "stale_after_hours": 48})
    assert rank_offers([o2], RankRequest(geo=GEOS["dhaka"]), FX, NOW) == []


def test_duty() -> None:
    assert estimate_duty_usd_micros("BD", "BD", 10_000_000, "mcu") == 0
    assert estimate_duty_usd_micros("CN", "BD", 10_000_000, "mcu") == 1_500_000
    assert estimate_duty_usd_micros("CN", "US", 50_000_000, "mcu") == 0  # under de minimis / no table


def test_geo() -> None:
    assert resolve_geo("BD", "Chittagong").city == "Chittagong"
    assert geo_from_headers({"CF-IPCountry": "BD", "cf-ipcity": "Sylhet"}).city == "Sylhet"
    assert geo_from_headers({"CF-IPCountry": "XX"}).country == "BD"
    assert 190 < haversine_km(23.8103, 90.4125, 24.8949, 91.8687) < 200
