"""Price alerts (§7.3): every 15 min; fire once per downward crossing (P4).

State machine per alert:
  armed   & price ≤ target                → FIRE   (armed := false, last_fired_at := now)
  disarmed & price > target × (1 + 2 %)    → REARM  (hysteresis stops flapping around the target)
  otherwise                                → nothing
"""

from __future__ import annotations

import asyncio
import enum
import smtplib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, PriceAlert, User
from crawler.normalizer.currency import from_minor
from price.fx import FxTable
from price.geo import resolve_geo
from price.ranker import RankRequest, SortMode, rank_offers
from price.repository import fetch_active_offers, fetch_ship_quotes

REARM_HYSTERESIS = Decimal("0.02")


class Transition(enum.StrEnum):
    FIRE = "fire"
    REARM = "rearm"
    NONE = "none"


def transition(armed: bool, current_minor: int, target_minor: int) -> Transition:
    if armed and current_minor <= target_minor:
        return Transition.FIRE
    if not armed and Decimal(current_minor) > Decimal(target_minor) * (1 + REARM_HYSTERESIS):
        return Transition.REARM
    return Transition.NONE


@dataclass(frozen=True)
class AlertMessage:
    to: str
    component_title: str
    component_slug: str
    price: Decimal
    currency: str
    source_name: str
    url: str


class Notifier(Protocol):
    async def send(self, msg: AlertMessage) -> None: ...


class SmtpNotifier:
    def __init__(
        self, host: str, port: int, sender: str, username: str = "", password: str = "", site_url: str = ""
    ) -> None:
        self.host, self.port, self.sender = host, port, sender
        self.username, self.password, self.site_url = username, password, site_url

    def _send_sync(self, msg: AlertMessage) -> None:
        em = EmailMessage()
        em["From"] = self.sender
        em["To"] = msg.to
        em["Subject"] = f"Price drop: {msg.component_title} now {msg.currency} {msg.price:,.2f}"
        em.set_content(
            f"{msg.component_title} is now {msg.currency} {msg.price:,.2f} (landed, per unit) at {msg.source_name}.\n\n"
            f"View at {msg.source_name}: {msg.url}\n"
            f"All offers: {self.site_url}/component/{msg.component_slug}\n\n"
            f"Manage or delete your alerts: {self.site_url}/alerts\n"
        )
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.username:
                smtp.starttls()
                smtp.login(self.username, self.password)
            smtp.send_message(em)

    async def send(self, msg: AlertMessage) -> None:
        await asyncio.to_thread(self._send_sync, msg)


async def evaluate_alerts(s: AsyncSession, fx: FxTable, now: datetime, notifier: Notifier) -> dict[str, int]:
    counts = {"checked": 0, "fired": 0, "rearmed": 0}
    rows = (
        await s.execute(
            select(PriceAlert, User.email, Component.title, Component.slug)
            .join(User, User.id == PriceAlert.user_id)
            .join(Component, Component.id == PriceAlert.component_id)
            .where(PriceAlert.active.is_(True))
        )
    ).all()
    for alert, email, title, slug in rows:
        counts["checked"] += 1
        geo = resolve_geo(alert.ship_to)
        offers = await fetch_active_offers(s, alert.component_id)
        quotes = await fetch_ship_quotes(s, list({o.source_id for o in offers}), geo.country)
        ranked = rank_offers(
            offers,
            RankRequest(geo=geo, quantity=alert.quantity, mode=SortMode.CHEAPEST, in_stock_only=True),
            fx,
            now,
            quotes,
        )
        if not ranked:
            continue
        best = ranked[0]
        current = fx.from_usd_micros(best.unit_landed_usd_micros, alert.currency)
        t = transition(alert.armed, current, alert.target_minor)
        if t is Transition.FIRE:
            await notifier.send(
                AlertMessage(
                    to=email,
                    component_title=title,
                    component_slug=slug,
                    price=from_minor(current, alert.currency),
                    currency=alert.currency,
                    source_name=best.offer.source_name,
                    url=best.offer.url,
                )
            )
            alert.armed = False
            alert.last_fired_at = now
            counts["fired"] += 1
        elif t is Transition.REARM:
            alert.armed = True
            counts["rearmed"] += 1
    await s.flush()
    return counts
