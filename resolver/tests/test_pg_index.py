"""Resolver against real Postgres: candidates, create, attach, review, merge, split, audit (R3)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Listing, MergeAudit, ReviewItem, Source
from resolver.embedder import HashingEmbedder
from resolver.matcher import Action
from resolver.merge_audit import MergeRefusedError, merge_components, resolve_review_item, split_component
from resolver.pg_index import PgComponentIndex
from resolver.service import ResolvableListing, Resolver

pytestmark = pytest.mark.db


async def _source(db: AsyncSession) -> uuid.UUID:
    s = Source(name="t", display_name="T", domain="t.test", type="crawl", base_url="https://t.test")
    db.add(s)
    await db.flush()
    return s.id


async def _listing(db: AsyncSession, source_id: uuid.UUID, title: str, **kw: object) -> uuid.UUID:
    lid = uuid.uuid4()
    db.add(Listing(id=lid, source_id=source_id, url=f"https://t.test/{lid}", url_hash=str(lid), raw_title=title, **kw))
    await db.flush()
    return lid


def _item(lid: uuid.UUID, title: str, mpn: str | None, mfr: str | None, **kw: Any) -> ResolvableListing:
    return ResolvableListing(
        id=lid,
        title=title,
        mpn=mpn,
        mpn_trusted=mpn is not None,
        manufacturer=mfr,
        gtin=kw.get("gtin"),
        package=kw.get("package"),
        specs=kw.get("specs", {}),
        datasheet_url=kw.get("datasheet_url"),
    )


async def test_create_then_attach_with_audit(db: AsyncSession) -> None:
    sid = await _source(db)
    r = Resolver(PgComponentIndex(db), HashingEmbedder())
    l1 = await _listing(db, sid, "ESP32-WROOM-32 module")
    l2 = await _listing(db, sid, "ESP32 WROOM 32 WiFi module")
    d1 = await r.resolve(
        _item(
            l1,
            "Espressif ESP32-WROOM-32 module",
            "ESP32-WROOM-32",
            "Espressif Systems",
            datasheet_url="https://www.espressif.com/ds.pdf",
        )
    )
    d2 = await r.resolve(_item(l2, "ESP32 WROOM 32 WiFi module", None, None))
    await db.commit()
    assert d1.action is Action.CREATE and d2.action is Action.ATTACH
    assert d1.component_id == d2.component_id
    comp = await db.get(Component, d1.component_id)
    assert comp is not None
    assert comp.slug == "esp32-wroom-32" and comp.manufacturer == "Espressif"
    assert comp.category == "wireless" and comp.embedding is not None
    audits = (await db.execute(select(MergeAudit.action, MergeAudit.listing_id))).all()
    assert ("create", l1) in audits and ("attach", l1) in audits and ("attach", l2) in audits
    assert (await db.get(Listing, l2)).match_method == "mpn_exact"  # type: ignore[union-attr]


async def test_review_and_resolve(db: AsyncSession) -> None:
    sid = await _source(db)
    r = Resolver(PgComponentIndex(db), HashingEmbedder())
    l1 = await _listing(db, sid, "x")
    l2 = await _listing(db, sid, "x")
    l3 = await _listing(db, sid, "x")
    await r.resolve(_item(l1, "TI LM7805CT", "LM7805CT", "onsemi"))
    await r.resolve(_item(l2, "ST LM7805CT", "LM7805CT", "STMicroelectronics"))
    d = await r.resolve(_item(l3, "LM7805CT regulator", None, None))  # two manufacturers → review
    await db.commit()
    assert d.action is Action.REVIEW
    item = (await db.execute(select(ReviewItem).where(ReviewItem.ref_id == str(l3)))).scalar_one()
    target = (await db.get(Listing, l1)).component_id  # type: ignore[union-attr]
    await resolve_review_item(db, item.id, component_id=target, actor="admin:test")
    await db.commit()
    assert (await db.get(Listing, l3)).component_id == target  # type: ignore[union-attr]
    assert (
        await db.execute(select(func.count()).select_from(MergeAudit).where(MergeAudit.listing_id == l3))
    ).scalar() == 1


async def test_merge_requires_threshold_and_audits(db: AsyncSession) -> None:
    sid = await _source(db)
    a = Component(
        slug="a",
        mpn="NE555P",
        mpn_norm="ne555p",
        manufacturer="Texas Instruments",
        manufacturer_norm="texasinstruments",
        category="ic-analog",
        title="a",
        gtin="00751492000015",
    )
    b = Component(
        slug="b",
        mpn="NE555P-X",
        mpn_norm="ne555px",
        manufacturer=None,
        manufacturer_norm="",
        category="ic-analog",
        title="b",
        gtin="00751492000015",
    )
    c = Component(
        slug="c",
        mpn="LM358N",
        mpn_norm="lm358n",
        manufacturer="Texas Instruments",
        manufacturer_norm="texasinstruments",
        category="ic-analog",
        title="c",
    )
    db.add_all([a, b, c])
    await db.flush()
    lb = await _listing(db, sid, "b", component_id=b.id)
    moved = await merge_components(db, a.id, b.id, actor="resolver")
    assert moved == 1
    assert (await db.get(Listing, lb)).component_id == a.id  # type: ignore[union-attr]
    assert (await db.get(Component, b.id)).status == "merged"  # type: ignore[union-attr]
    with pytest.raises(MergeRefusedError):
        await merge_components(db, a.id, c.id, actor="resolver")  # different parts, no force
    rows = (await db.execute(select(MergeAudit.action).where(MergeAudit.from_component == b.id))).scalars().all()
    assert "merge" in rows and "attach" in rows


async def test_split_moves_listings_with_audit(db: AsyncSession) -> None:
    sid = await _source(db)
    comp = Component(
        slug="esp32-wroom-32",
        mpn="ESP32-WROOM-32",
        mpn_norm="esp32wroom32",
        manufacturer="Espressif",
        manufacturer_norm="espressif",
        category="wireless",
        title="x",
    )
    db.add(comp)
    await db.flush()
    keep = await _listing(db, sid, "32", component_id=comp.id)
    wrong = await _listing(db, sid, "32D", component_id=comp.id)
    new_id = await split_component(
        db, comp.id, [wrong], new_mpn="ESP32-WROOM-32D", new_manufacturer="Espressif", actor="admin:test"
    )
    await db.commit()
    assert (await db.get(Listing, wrong)).component_id == new_id  # type: ignore[union-attr]
    assert (await db.get(Listing, keep)).component_id == comp.id  # type: ignore[union-attr]
    assert (await db.get(Component, new_id)).slug == "esp32-wroom-32d"  # type: ignore[union-attr]
    split_rows = (await db.execute(select(MergeAudit).where(MergeAudit.action == "split"))).scalars().all()
    assert len(split_rows) == 1 and split_rows[0].details["moved_listings"] == [str(wrong)]
