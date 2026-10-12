"""Currency conversion on minor units.

Rates are stored as `per_usd` (units of currency per 1 USD) per day in `fx_rates`.
Source: open.er-api.com (daily, includes BDT; ECB reference rates do not cover BDT).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.http import ApiClient
from common.models import FxRate
from common.timeutil import utcnow
from crawler.normalizer.currency import minor_exponent

DEFAULT_PROVIDER = "https://open.er-api.com/v6/latest/USD"


class UnknownCurrencyError(KeyError):
    pass


@dataclass(frozen=True)
class FxTable:
    day: date
    per_usd: dict[str, Decimal]

    def __post_init__(self) -> None:
        rates = {k.upper(): v for k, v in self.per_usd.items()}
        rates["USD"] = Decimal(1)
        object.__setattr__(self, "per_usd", rates)

    def rate(self, currency: str) -> Decimal:
        try:
            return self.per_usd[currency.upper()]
        except KeyError as exc:
            raise UnknownCurrencyError(currency) from exc

    def convert_minor(self, amount_minor: int, from_cur: str, to_cur: str) -> int:
        if from_cur.upper() == to_cur.upper():
            return amount_minor
        major = Decimal(amount_minor) / (Decimal(10) ** minor_exponent(from_cur))
        usd = major / self.rate(from_cur)
        target = usd * self.rate(to_cur)
        scaled = target * (Decimal(10) ** minor_exponent(to_cur))
        return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def to_usd_micros(self, amount_minor: int, currency: str) -> int:
        """Exact-enough internal unit for ranking: 1e-6 USD (cents lose ~৳1 per conversion)."""
        major = Decimal(amount_minor) / (Decimal(10) ** minor_exponent(currency))
        return int((major / self.rate(currency) * 1_000_000).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def from_usd_micros(self, micros: int, currency: str) -> int:
        major = Decimal(micros) / 1_000_000 * self.rate(currency)
        return int((major * (Decimal(10) ** minor_exponent(currency))).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def to_usd_minor(self, amount_minor: int, currency: str) -> int:
        return self.convert_minor(amount_minor, currency, "USD")

    def from_usd_minor(self, usd_minor: int, currency: str) -> int:
        return self.convert_minor(usd_minor, "USD", currency)

    def convert_major(self, amount: Decimal, from_cur: str, to_cur: str) -> Decimal:
        if from_cur.upper() == to_cur.upper():
            return amount
        return amount / self.rate(from_cur) * self.rate(to_cur)


async def fetch_rates(client: ApiClient, url: str = DEFAULT_PROVIDER) -> dict[str, Decimal]:
    data = await client.get_json(url)
    if data.get("result") not in (None, "success"):
        raise RuntimeError(f"FX provider error: {data.get('error-type') or data}")
    rates = data.get("rates") or {}
    out = {str(k).upper(): Decimal(str(v)) for k, v in rates.items() if v and Decimal(str(v)) > 0}
    if "BDT" not in out:
        raise RuntimeError("FX provider did not return BDT")
    out["USD"] = Decimal(1)
    return out


async def store_rates(s: AsyncSession, day: date, rates: dict[str, Decimal], source: str) -> int:
    for cur, per_usd in rates.items():
        stmt = insert(FxRate).values(day=day, currency=cur, per_usd=per_usd, source=source)
        await s.execute(
            stmt.on_conflict_do_update(index_elements=["day", "currency"], set_={"per_usd": per_usd, "source": source})
        )
    return len(rates)


async def load_table(s: AsyncSession, day: date | None = None) -> FxTable:
    """Latest rates on or before `day` (per currency), so a missed fetch never blocks pricing."""
    day = day or utcnow().date()
    rows = (
        await s.execute(
            select(FxRate.currency, FxRate.per_usd, FxRate.day)
            .where(FxRate.day <= day)
            .order_by(FxRate.currency, FxRate.day.desc())
            .ext(distinct_on(FxRate.currency))
        )
    ).all()
    if not rows:
        raise RuntimeError("no FX rates stored; run the fx.refresh task")
    return FxTable(day=max(r[2] for r in rows), per_usd={r[0]: Decimal(r[1]) for r in rows})
