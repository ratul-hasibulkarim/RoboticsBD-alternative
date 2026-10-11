"""Builds Typesense documents from Postgres and upserts them."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Component, Image, Listing, PriceCurrent, Source
from common.settings import Settings, get_settings
from search.typesense import TypesenseClient

HERE = Path(__file__).parent
SCHEMA: dict[str, Any] = json.loads((HERE / "schema.json").read_text())
SYNONYMS: dict[str, list[str]] = json.loads((HERE / "synonyms.json").read_text())
COLLECTION = SCHEMA["name"]


def typesense_client(settings: Settings | None = None) -> TypesenseClient:
    s = settings or get_settings()
    return TypesenseClient(
        f"{s.typesense_protocol}://{s.typesense_host}:{s.typesense_port}", s.typesense_api_key.get_secret_value()
    )


def specs_text(specs: dict[str, Any]) -> str:
    return " ".join(f"{k} {v}" for k, v in specs.items())[:2000]


async def build_documents(s: AsyncSession, component_ids: list[uuid.UUID] | None = None) -> list[dict[str, Any]]:
    offer_stats = (
        select(
            Listing.component_id.label("cid"),
            func.min(PriceCurrent.landed_usd_minor).filter(Listing.in_stock.is_not(False)).label("lowest"),
            func.count(PriceCurrent.listing_id).label("offers"),
            func.bool_or(Listing.in_stock.is_(True)).label("in_stock"),
            func.bool_or(
                func.coalesce(func.array_position(Listing.ships_to, "BD"), func.array_position(Listing.ships_to, "*"))
                .is_not(None)
            ).label("ships_bd"),
        )
        .join(PriceCurrent, PriceCurrent.listing_id == Listing.id)
        .join(Source, and_(Source.id == Listing.source_id, Source.active.is_(True), Source.legal_review_status != "blocked"))
        .where(Listing.active.is_(True), Listing.component_id.is_not(None))
        .group_by(Listing.component_id)
        .subquery()
    )
    q = (
        select(Component, offer_stats.c.lowest, offer_stats.c.offers, offer_stats.c.in_stock, offer_stats.c.ships_bd,
               Image.source_url)
        .outerjoin(offer_stats, offer_stats.c.cid == Component.id)
        .outerjoin(Image, Image.id == Component.primary_image)
        .where(Component.status == "active")
    )
    if component_ids is not None:
        q = q.where(Component.id.in_(component_ids))
    docs: list[dict[str, Any]] = []
    for comp, lowest, offers, in_stock, ships_bd, image_url in (await s.execute(q)).all():
        doc: dict[str, Any] = {
            "id": str(comp.id),
            "slug": comp.slug,
            "mpn": comp.mpn,
            "mpn_norm": comp.mpn_norm,
            "title": comp.title,
            "category": comp.category,
            "offer_count": int(offers or 0),
            "in_stock": bool(in_stock),
            "ships_to_bd": bool(ships_bd),
            "popularity": float(comp.popularity),
            "specs_text": specs_text(comp.specs or {}),
        }
        for key, val in (("manufacturer", comp.manufacturer), ("subcategory", comp.subcategory),
                         ("package", comp.package), ("image_url", image_url)):
            if val:
                doc[key] = val
        if lowest is not None:
            doc["lowest_price_usd_minor"] = int(lowest)
        if comp.embedding is not None:
            doc["embedding"] = [float(x) for x in comp.embedding]
        docs.append(doc)
    return docs


async def ensure_schema(ts: TypesenseClient) -> None:
    await ts.ensure_collection(SCHEMA)
    await ts.upsert_synonyms(COLLECTION, SYNONYMS)


async def index_components(s: AsyncSession, ts: TypesenseClient, component_ids: list[uuid.UUID] | None = None) -> int:
    docs = await build_documents(s, component_ids)
    if component_ids is not None:
        found = {d["id"] for d in docs}
        for cid in component_ids:
            if str(cid) not in found:  # merged / retired → remove from index
                await ts.delete_document(COLLECTION, str(cid))
    total = 0
    for i in range(0, len(docs), 500):
        total += await ts.import_documents(COLLECTION, docs[i : i + 500])
    return total
