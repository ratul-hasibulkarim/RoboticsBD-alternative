"""Import duty ESTIMATES by destination country and component category.

These are deliberately coarse, labelled "estimate" everywhere they are shown, and are
configuration rather than law: the owner must review them against the destination's
current tariff schedule (for Bangladesh: NBR customs tariff, HS chapters 85 and 90)
before launch. Domestic shipments (ships_from == destination) carry no duty.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# destination → category → total tax incidence on CIF value (customs + supplementary + VAT + AIT …)
DUTY_RATES: dict[str, dict[str, Decimal]] = {
    "BD": {
        "mcu": Decimal("0.15"),
        "ic-analog": Decimal("0.15"),
        "ic-logic": Decimal("0.15"),
        "ic-interface": Decimal("0.15"),
        "semiconductor": Decimal("0.15"),
        "wireless": Decimal("0.31"),
        "sensor": Decimal("0.31"),
        "dev-board": Decimal("0.31"),
        "power": Decimal("0.31"),
        "motor-driver": Decimal("0.31"),
        "display": Decimal("0.31"),
        "passive": Decimal("0.31"),
        "connector": Decimal("0.31"),
        "relay": Decimal("0.31"),
        "motor": Decimal("0.37"),
        "battery": Decimal("0.37"),
        "tool": Decimal("0.37"),
        "_default": Decimal("0.31"),
    },
    "IN": {"_default": Decimal("0.20")},
}
# Below this CIF value (USD minor units) no duty is assessed (de minimis); None = no threshold.
DE_MINIMIS_USD_MINOR: dict[str, int | None] = {"BD": None, "IN": None, "US": 80000, "GB": 13500, "DE": 15000}


def duty_rate(dest_country: str, category: str | None) -> Decimal:
    table = DUTY_RATES.get(dest_country.upper())
    if not table:
        return Decimal(0)
    return table.get(category or "_default", table["_default"])


def estimate_duty_usd_micros(
    ships_from: str | None, dest_country: str, cif_usd_micros: int, category: str | None
) -> int:
    """Duty on the CIF value (goods + shipping), in 1e-6 USD."""
    if not dest_country or (ships_from and ships_from.upper() == dest_country.upper()):
        return 0
    threshold = DE_MINIMIS_USD_MINOR.get(dest_country.upper())
    if threshold is not None and cif_usd_micros <= threshold * 10_000:
        return 0
    rate = duty_rate(dest_country, category)
    return int((Decimal(cif_usd_micros) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))
