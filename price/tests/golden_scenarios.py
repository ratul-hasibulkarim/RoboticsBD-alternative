"""Scenario definitions for the P2 golden ranker set (10 scenarios × 5 user locations = 50 cases).

Expected top-3 orders live in golden_ranker.json; they were produced by
scripts/regen_ranker_golden.py and then checked by hand against the reasoning noted
next to each scenario below. Re-generate only for deliberate ranking changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from price.fx import FxTable
from price.geo import resolve_geo
from price.ranker import Offer, PriceBreakMinor, ShipQuote

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
FX = FxTable(
    day=NOW.date(), per_usd={"BDT": Decimal("122"), "EUR": Decimal("0.92"), "INR": Decimal("84"), "CNY": Decimal("7.2")}
)

GEOS = {
    "dhaka": resolve_geo("BD", "dhaka"),
    "chattogram": resolve_geo("BD", "chattogram"),
    "sylhet": resolve_geo("BD", "sylhet"),
    "delhi": resolve_geo("IN", "delhi"),
    "berlin": resolve_geo("DE", "berlin"),
}

# name: (id, ships_from, ships_to, lat, lon, trust)
SOURCES = {
    "RoboticsBD": (uuid.UUID(int=1), "BD", ("BD",), 23.8103, 90.4125, 0.8),
    "TechShop BD": (uuid.UUID(int=2), "BD", ("BD",), 23.7465, 90.3760, 0.8),
    "Ctg Electronics": (uuid.UUID(int=3), "BD", ("BD",), 22.3569, 91.7832, 0.7),
    "LCSC": (uuid.UUID(int=4), "CN", ("*",), 22.5431, 114.0579, 0.95),
    "Mouser": (uuid.UUID(int=5), "US", ("*",), 32.5632, -97.1417, 0.98),
    "DigiKey": (uuid.UUID(int=6), "US", ("*",), 48.1191, -96.1781, 0.98),
    "Kolkata Parts": (uuid.UUID(int=7), "IN", ("IN", "BD"), 22.5726, 88.3639, 0.6),
}

# (source_id, to_country) → quote
QUOTES = {
    (SOURCES["LCSC"][0], "BD"): ShipQuote(800, "USD", 7, 12),
    (SOURCES["LCSC"][0], "IN"): ShipQuote(700, "USD", 6, 10),
    (SOURCES["LCSC"][0], "DE"): ShipQuote(1000, "USD", 6, 10),
    (SOURCES["Mouser"][0], "BD"): ShipQuote(2000, "USD", 4, 6),
    (SOURCES["Mouser"][0], "IN"): ShipQuote(2000, "USD", 3, 5),
    (SOURCES["Mouser"][0], "DE"): ShipQuote(0, "USD", 2, 3),
    (SOURCES["DigiKey"][0], "BD"): ShipQuote(2500, "USD", 3, 5),
    (SOURCES["DigiKey"][0], "IN"): ShipQuote(2000, "USD", 3, 5),
    (SOURCES["DigiKey"][0], "DE"): ShipQuote(0, "USD", 2, 4),
    (SOURCES["Kolkata Parts"][0], "BD"): ShipQuote(30000, "INR", 5, 9),
    (SOURCES["Kolkata Parts"][0], "IN"): ShipQuote(10000, "INR", 2, 4),
}


def offer(
    source: str,
    currency: str,
    price_minor: int,
    *,
    age_days: float = 0.0,
    in_stock: bool | None = True,
    breaks: tuple[tuple[int, int], ...] = (),
    moq: int = 1,
    category: str = "mcu",
) -> Offer:
    sid, frm, to, lat, lon, trust = SOURCES[source]
    return Offer(
        listing_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{source}/{currency}/{price_minor}/{age_days}"),
        source_id=sid,
        source_name=source,
        url=f"https://{source.lower().replace(' ', '')}.test/p",
        currency=currency,
        price_minor=price_minor,
        observed_at=NOW - timedelta(days=age_days),
        price_breaks=tuple(PriceBreakMinor(q, p) for q, p in breaks),
        moq=moq,
        ships_from=frm,
        ships_to=to,
        warehouse_lat=lat,
        warehouse_lon=lon,
        trust_score=trust,
        in_stock=in_stock,
        category=category,
    )


# scenario → (quantity, offers). Reasoning for the hand check:
SCENARIOS: dict[str, tuple[int, list[Offer]]] = {
    # 1. ESP32 module: BD shops ~৳520–560, LCSC $2.80 + $8 ship. In BD local shops win on cost+speed.
    "esp32_qty1": (
        1,
        [
            offer("RoboticsBD", "BDT", 52000),
            offer("TechShop BD", "BDT", 56000),
            offer("LCSC", "USD", 280),
            offer("Mouser", "USD", 520),
            offer("DigiKey", "USD", 510),
        ],
    ),
    # 2. Same part at qty 100: LCSC price break ($2.10) amortises shipping → LCSC competitive on cost.
    "esp32_qty100": (
        100,
        [
            offer("RoboticsBD", "BDT", 52000),
            offer("TechShop BD", "BDT", 50000, breaks=((1, 56000), (50, 50000))),
            offer("LCSC", "USD", 280, breaks=((1, 280), (100, 210))),
            offer("Mouser", "USD", 520, breaks=((1, 520), (100, 400))),
        ],
    ),
    # 3. Cheap resistor where BD shop is out of stock: in-stock offers must rank above it.
    "resistor_oos": (
        1,
        [
            offer("RoboticsBD", "BDT", 100, in_stock=False, category="passive"),
            offer("TechShop BD", "BDT", 150, category="passive"),
            offer("LCSC", "USD", 2, moq=100, category="passive"),
        ],
    ),
    # 4. Stale price: a 45-day-old cheaper BD price vs fresh slightly dearer one.
    "stale_vs_fresh": (
        1,
        [
            offer("RoboticsBD", "BDT", 40000, age_days=45),
            offer("TechShop BD", "BDT", 42000),
            offer("Ctg Electronics", "BDT", 41000, age_days=1),
        ],
    ),
    # 5. Chattogram shop: equal price → proximity decides for Chattogram users.
    "proximity_tie": (
        1,
        [offer("RoboticsBD", "BDT", 30000), offer("Ctg Electronics", "BDT", 30000), offer("TechShop BD", "BDT", 30000)],
    ),
    # 6. Indian shop ships to BD/IN: cheap item price but ৳ shipping from Kolkata.
    "india_shop": (
        1,
        [offer("Kolkata Parts", "INR", 15000), offer("RoboticsBD", "BDT", 26000), offer("LCSC", "USD", 150)],
    ),
    # 7. Only global distributors carry it (e.g. STM32H7): ordering by landed cost/ETA.
    "global_only": (1, [offer("Mouser", "USD", 1450), offer("DigiKey", "USD", 1420), offer("LCSC", "USD", 1180)]),
    # 8. MOQ trap: LCSC MOQ 10 at $0.05 vs BD shop ৳15 per piece — per-unit landed decides.
    "moq_trap": (
        1,
        [
            offer("LCSC", "USD", 5, moq=10, category="semiconductor"),
            offer("TechShop BD", "BDT", 1500, category="semiconductor"),
            offer("RoboticsBD", "BDT", 1200, category="semiconductor"),
        ],
    ),
    # 9. Expensive dev board: duty on imports makes BD stock more attractive in BD.
    "devboard_duty": (
        1,
        [
            offer("RoboticsBD", "BDT", 1250000, category="dev-board"),
            offer("Mouser", "USD", 8000, category="dev-board"),
            offer("DigiKey", "USD", 7900, category="dev-board"),
            offer("LCSC", "USD", 7600, category="dev-board"),
        ],
    ),
    # 10. Unknown stock everywhere, similar costs: trust and freshness break ties.
    "unknown_stock": (
        1,
        [
            offer("TechShop BD", "BDT", 20000, in_stock=None),
            offer("RoboticsBD", "BDT", 20000, in_stock=None, age_days=10),
            offer("Ctg Electronics", "BDT", 19800, in_stock=None, age_days=20),
        ],
    ),
}
