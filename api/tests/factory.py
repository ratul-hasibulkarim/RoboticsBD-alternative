"""Builds a small, realistic dataset for API / web tests (shared with scripts/seed_demo_data.py)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Datasheet, Listing, Source, UseCase
from crawler.normalizer.mpn import manufacturer_key, mpn_key
from crawler.normalizer.units import normalize_specs
from price.fx import FxTable, store_rates
from price.snapshotter import Observation, record
from resolver.categorize import categorize, slugify
from resolver.embedder import HashingEmbedder, embedding_text

FX_RATES = {
    "USD": Decimal("1"),
    "BDT": Decimal("122"),
    "EUR": Decimal("0.92"),
    "INR": Decimal("84"),
    "CNY": Decimal("7.2"),
}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    display: str
    domain: str
    country: str
    currency: str
    ships_to: tuple[str, ...]
    lat: float
    lon: float
    trust: float
    affiliate: str | None = None


SOURCES = [
    SourceSpec(
        "demo-robotics-bd", "Demo Robotics BD", "demo-robotics.test", "BD", "BDT", ("BD",), 23.8103, 90.4125, 0.8
    ),
    SourceSpec(
        "demo-techshop-bd", "Demo TechShop BD", "demo-techshop.test", "BD", "BDT", ("BD",), 23.7465, 90.3760, 0.8
    ),
    SourceSpec("demo-ctg-parts", "Demo Ctg Parts", "demo-ctg.test", "BD", "BDT", ("BD",), 22.3569, 91.7832, 0.7),
    SourceSpec(
        "demo-global-dist",
        "Demo Global Distributor",
        "demo-global.test",
        "US",
        "USD",
        ("*",),
        32.56,
        -97.14,
        0.95,
        "https://aff.demo-global.test/r?u={url}",
    ),
]


async def add_sources(s: AsyncSession) -> dict[str, uuid.UUID]:
    out = {}
    for sp in SOURCES:
        src = Source(
            name=sp.name,
            display_name=sp.display,
            domain=sp.domain,
            type="crawl",
            base_url=f"https://{sp.domain}",
            country=sp.country,
            currency=sp.currency,
            legal_review_status="approved",
            legal_reviewed_by="demo",
            ships_to=list(sp.ships_to),
            warehouse_country=sp.country,
            warehouse_lat=sp.lat,
            warehouse_lon=sp.lon,
            trust_score=Decimal(str(sp.trust)),
            affiliate_template=sp.affiliate,
            cache_ttl_hours=48,
        )
        s.add(src)
        await s.flush()
        out[sp.name] = src.id
    return out


async def add_component(
    s: AsyncSession,
    mpn: str,
    manufacturer: str | None,
    title: str,
    specs: dict[str, str],
    *,
    package: str | None = None,
    datasheet: str | None = None,
    popularity: float = 0.0,
) -> Component:
    human, machine = normalize_specs(specs)
    cat, sub = categorize(title)
    emb = HashingEmbedder().embed([embedding_text(manufacturer, mpn, title, human)])[0]
    comp = Component(
        slug=slugify(mpn),
        mpn=mpn,
        mpn_norm=mpn_key(mpn),
        manufacturer=manufacturer,
        manufacturer_norm=manufacturer_key(manufacturer),
        category=cat,
        subcategory=sub,
        title=title,
        specs=human,
        specs_norm=machine,
        package=package,
        embedding=emb,
        popularity=popularity,
        datasheet_url=datasheet,
        short_desc=title,
    )
    s.add(comp)
    await s.flush()
    if datasheet:
        s.add(Datasheet(component_id=comp.id, url=datasheet, host=datasheet.split("/")[2], is_primary=True))
    return comp


async def add_offer(
    s: AsyncSession,
    fx: FxTable,
    source_id: uuid.UUID,
    comp: Component,
    price: Decimal,
    currency: str,
    *,
    in_stock: bool = True,
    ships_from: str = "BD",
    ships_to: tuple[str, ...] = ("BD",),
    observed: datetime,
    image: str | None = None,
) -> uuid.UUID:
    lid = uuid.uuid4()
    s.add(
        Listing(
            id=lid,
            source_id=source_id,
            url=f"https://shop.test/{comp.slug}/{lid.hex[:6]}",
            url_hash=lid.hex,
            raw_title=f"{comp.mpn} {comp.title}",
            raw_mpn=comp.mpn,
            mpn_trusted=True,
            component_id=comp.id,
            match_confidence=Decimal("0.98"),
            match_method="mpn_exact",
            in_stock=in_stock,
            ships_from=ships_from,
            ships_to=list(ships_to),
            image_url=image,
        )
    )
    await s.flush()
    await record(s, Observation(lid, currency, price, observed), fx)
    return lid


async def seed_small(s: AsyncSession, now: datetime) -> dict[str, object]:
    await store_rates(s, now.date(), FX_RATES, "test")
    fx = FxTable(day=now.date(), per_usd=dict(FX_RATES))
    src = await add_sources(s)
    esp = await add_component(
        s,
        "ESP32-WROOM-32",
        "Espressif",
        "ESP32-WROOM-32 Wi-Fi + Bluetooth module",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "240MHz"},
        package="SMD-38",
        datasheet="https://www.espressif.com/esp32-wroom-32_datasheet_en.pdf",
        popularity=10,
    )
    esp_d = await add_component(
        s,
        "ESP32-WROOM-32D",
        "Espressif",
        "ESP32-WROOM-32D Wi-Fi + Bluetooth module",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "240MHz"},
        package="SMD-38",
        popularity=5,
    )
    ne555 = await add_component(
        s,
        "NE555P",
        "Texas Instruments",
        "NE555P precision timer IC",
        {"Supply Voltage": "4.5V ~ 16V"},
        package="DIP-8",
        popularity=8,
    )
    await add_offer(
        s,
        fx,
        src["demo-robotics-bd"],
        esp,
        Decimal("520"),
        "BDT",
        observed=now - timedelta(hours=2),
        image="https://demo-robotics.test/esp32.jpg",
    )
    await add_offer(s, fx, src["demo-techshop-bd"], esp, Decimal("560"), "BDT", observed=now - timedelta(hours=1))
    await add_offer(
        s,
        fx,
        src["demo-global-dist"],
        esp,
        Decimal("5.20"),
        "USD",
        ships_from="US",
        ships_to=("*",),
        observed=now - timedelta(hours=3),
    )
    await add_offer(s, fx, src["demo-robotics-bd"], esp_d, Decimal("540"), "BDT", observed=now - timedelta(hours=2))
    await add_offer(s, fx, src["demo-ctg-parts"], ne555, Decimal("15"), "BDT", observed=now - timedelta(days=1))
    s.add(
        UseCase(
            component_id=esp.id,
            slug="blink-led-arduino",
            title="Blink an LED with ESP32 (Arduino core)",
            difficulty="beginner",
            summary="Install the ESP32 Arduino core and toggle GPIO2.",
            steps=["Install the core", "Upload sketch"],
            code_language="arduino",
            code_snippet="void setup(){pinMode(2,OUTPUT);}\nvoid loop(){digitalWrite(2,!digitalRead(2));delay(500);}",
            code_license="CC0-1.0",
            source_type="editorial",
            source_url="https://voltfind.com/guides/esp32-blink",
            source_author="VoltFind",
        )
    )
    await s.flush()
    return {"sources": src, "esp": esp, "esp_d": esp_d, "ne555": ne555, "today": date.today()}
