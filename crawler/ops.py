"""Pipeline operations (async, testable). crawler/tasks.py wraps each one in a Celery task.

seed_source      → product URLs (sitemap / category walkers)
fetch_and_extract→ Fetcher + extraction pipeline → listing upsert + price snapshot
resolve_listing  → Resolver (attach / create / review / defer) + primary image
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.hashing import canonical_url, url_hash
from common.models import (
    Component,
    ComponentImage,
    CrawlPage,
    Image,
    Listing,
    LlmExtractionLog,
    ReviewItem,
    Source,
)
from common.timeutil import utcnow
from crawler.extractors.llm import LlmExtractor
from crawler.extractors.pipeline import ExtractionResult, Outcome, extract
from crawler.extractors.types import ExtractedListing
from crawler.fetcher.worker import Fetcher, FetchStatus
from crawler.registry import SourceConfig
from price.fx import FxTable
from price.snapshotter import Observation, record
from resolver.embedder import Embedder
from resolver.matcher import Action
from resolver.pg_index import PgComponentIndex
from resolver.service import ResolvableListing, Resolver

MAX_CONSECUTIVE_FAILURES = 5


@dataclass(frozen=True)
class FetchExtractResult:
    fetch_status: FetchStatus
    outcome: Outcome | None
    listing_id: uuid.UUID | None
    retry_after_s: float | None = None


async def source_db_id(s: AsyncSession, name: str) -> uuid.UUID:
    sid = (await s.execute(select(Source.id).where(Source.name == name))).scalar_one_or_none()
    if sid is None:
        raise LookupError(f"source {name!r} not synced to DB; run `make sync-sources`")
    return sid


async def upsert_listing(s: AsyncSession, source_id: uuid.UUID, ex: ExtractedListing) -> uuid.UUID:
    now = utcnow()
    values = {
        "source_id": source_id,
        "url": canonical_url(ex.url),
        "url_hash": url_hash(ex.url),
        "source_sku": ex.sku,
        "gtin": ex.gtin,
        "raw_title": (ex.title or "")[:500],
        "raw_mpn": ex.mpn,
        "mpn_trusted": ex.mpn_trusted,
        "raw_manufacturer": ex.manufacturer,
        "package": ex.package,
        "specs": ex.specs,
        "image_url": ex.image_urls[0] if ex.image_urls else None,
        "datasheet_url": ex.datasheet_url,
        "snippet": ex.snippet,
        "condition": ex.condition or "new",
        "in_stock": ex.in_stock,
        "stock_qty": ex.stock_qty,
        "ships_from": ex.ships_from,
        "ships_to": ex.ships_to,
        "extraction_method": ",".join(ex.methods),
        "consecutive_failures": 0,
        "last_seen": now,
        "last_attempt": now,
        "active": True,
    }
    ins = insert(Listing).values(**values)
    stmt = ins.on_conflict_do_update(
        index_elements=["url_hash"], set_={k: ins.excluded[k] for k in values if k not in ("url_hash", "source_id")}
    ).returning(Listing.id)
    listing_id: uuid.UUID = (await s.execute(stmt)).scalar_one()
    return listing_id


async def _log_llm(s: AsyncSession, url: str, model: str, res: ExtractionResult) -> None:
    if res.llm is None:
        return
    s.add(
        LlmExtractionLog(
            url=url,
            model=model,
            input_hash=res.llm.input_hash,
            output=res.llm.raw,
            confidence=Decimal(str(res.llm.confidence)),
            cost_usd_micros=res.llm.cost_micros,
            committed=res.outcome is Outcome.OK_LLM,
            error=res.llm.error,
        )
    )


async def mark_failure(s: AsyncSession, url: str) -> None:
    h = url_hash(url)
    await s.execute(
        update(Listing)
        .where(Listing.url_hash == h)
        .values(consecutive_failures=Listing.consecutive_failures + 1, last_attempt=utcnow())
    )
    await s.execute(
        update(Listing)
        .where(Listing.url_hash == h, Listing.consecutive_failures >= MAX_CONSECUTIVE_FAILURES)
        .values(active=False)
    )


async def fetch_and_extract(
    sm: async_sessionmaker[AsyncSession],
    fetcher: Fetcher,
    source: SourceConfig,
    url: str,
    fx: FxTable,
    *,
    llm: LlmExtractor | None = None,
    llm_model: str = "",
) -> FetchExtractResult:
    async with sm() as s:
        sid = await source_db_id(s, source.name)
    res = await fetcher.fetch(url, source, sid)

    if res.status in (FetchStatus.NOT_MODIFIED, FetchStatus.UNCHANGED):
        async with sm() as s:
            await s.execute(
                update(Listing)
                .where(Listing.url_hash == url_hash(url))
                .values(last_seen=utcnow(), last_attempt=utcnow())
            )
            await s.commit()
        return FetchExtractResult(res.status, None, None)
    if res.status is not FetchStatus.OK or res.body is None:
        if res.status in (FetchStatus.HTTP_ERROR, FetchStatus.NETWORK_ERROR, FetchStatus.RETRY_LATER):
            async with sm() as s:
                await mark_failure(s, url)
                await s.commit()
        return FetchExtractResult(res.status, None, None, res.retry_after_s)

    result = await extract(res.body, res.final_url, source, llm=llm)
    async with sm() as s:
        await _log_llm(s, res.final_url, llm_model, result)
        await s.execute(update(CrawlPage).where(CrawlPage.url_hash == url_hash(url)).values(extracted_at=utcnow()))
        listing_id = None
        if result.committable and result.listing is not None:
            ex = result.listing
            listing_id = await upsert_listing(s, sid, ex)
            if ex.price is not None and ex.currency:
                await record(
                    s,
                    Observation(
                        listing_id=listing_id,
                        currency=ex.currency,
                        price=ex.price,
                        observed_at=utcnow(),
                        price_breaks=tuple((b.qty, b.price) for b in ex.price_breaks),
                        moq=ex.moq or 1,
                    ),
                    fx,
                )
        elif result.outcome is Outcome.REVIEW:
            s.add(
                ReviewItem(
                    kind="llm_extraction",
                    ref_id=url_hash(url),
                    reason="LLM confidence below threshold",
                    payload={
                        "url": res.final_url,
                        "listing": result.listing.model_dump(mode="json") if result.listing else None,
                    },
                )
            )
        await s.commit()
    return FetchExtractResult(res.status, result.outcome, listing_id)


def resolvable(listing: Listing) -> ResolvableListing:
    return ResolvableListing(
        id=listing.id,
        title=listing.raw_title,
        mpn=listing.raw_mpn,
        mpn_trusted=listing.mpn_trusted,
        manufacturer=listing.raw_manufacturer,
        gtin=listing.gtin,
        package=listing.package,
        specs=dict(listing.specs or {}),
        datasheet_url=listing.datasheet_url,
        snippet=listing.snippet,
    )


async def ensure_primary_image(s: AsyncSession, component_id: uuid.UUID, listing: Listing, source_name: str) -> None:
    comp = await s.get(Component, component_id)
    if comp is None or comp.primary_image is not None or not listing.image_url:
        return
    img_id = (
        await s.execute(
            insert(Image)
            .values(
                source_id=listing.source_id,
                source_url=listing.image_url,
                attribution=f"Image: {source_name}",
                license="source-hosted",
            )
            .on_conflict_do_update(index_elements=["source_url"], set_={"attribution": f"Image: {source_name}"})
            .returning(Image.id)
        )
    ).scalar_one()
    await s.execute(
        insert(ComponentImage).values(component_id=component_id, image_id=img_id, position=0).on_conflict_do_nothing()
    )
    comp.primary_image = img_id


async def resolve_listing(
    s: AsyncSession, listing_id: uuid.UUID, embedder: Embedder, *, allow_untrusted_create: bool
) -> tuple[Action, uuid.UUID | None]:
    listing = await s.get(Listing, listing_id)
    if listing is None:
        return Action.REVIEW, None
    if listing.component_id is not None and listing.match_method == "manual":
        return Action.ATTACH, listing.component_id  # never override an admin decision
    resolver = Resolver(PgComponentIndex(s), embedder)
    d = await resolver.resolve(resolvable(listing), allow_untrusted_create=allow_untrusted_create)
    cid = (await s.get(Listing, listing_id)).component_id  # type: ignore[union-attr]
    if cid is not None:
        src_name = (await s.execute(select(Source.display_name).where(Source.id == listing.source_id))).scalar_one()
        await ensure_primary_image(s, cid, listing, src_name)
    return d.action, cid


DEFER_DELAY = timedelta(hours=24)


async def purge_expired_raw(s: AsyncSession, raw_delete: object) -> int:
    """Delete raw HTML older than its TTL (LEGAL rule 7). raw_delete: async callable(ref)."""
    now = utcnow()
    rows = (
        await s.execute(
            select(CrawlPage.id, CrawlPage.raw_ref).where(CrawlPage.raw_ref.is_not(None), CrawlPage.expires_at < now)
        )
    ).all()
    for pid, ref in rows:
        await raw_delete(ref)  # type: ignore[operator]
        await s.execute(update(CrawlPage).where(CrawlPage.id == pid).values(raw_ref=None))
    return len(rows)


async def ingest_api_listings(
    s: AsyncSession, source_name: str, listings: list[ExtractedListing], fx: FxTable
) -> list[uuid.UUID]:
    """Official-API results take the same path as crawled pages: listing upsert + price snapshot."""
    from crawler.extractors.pii import scrub

    sid = await source_db_id(s, source_name)
    ids = []
    for ex in listings:
        ex = ex.model_copy(update={"snippet": scrub(ex.snippet)})
        lid = await upsert_listing(s, sid, ex)
        if ex.price is not None and ex.currency:
            await record(
                s,
                Observation(
                    lid, ex.currency, ex.price, utcnow(), tuple((b.qty, b.price) for b in ex.price_breaks), ex.moq or 1
                ),
                fx,
            )
        ids.append(lid)
    return ids


async def ingest_use_cases(s: AsyncSession, component_id: uuid.UUID, drafts: list[Any]) -> int:
    """Store use-case drafts (summary + link; code only with a permissive license)."""
    from common.models import UseCase
    from resolver.categorize import slugify

    n = 0
    for d in drafts:
        values = {
            "component_id": component_id,
            "slug": slugify(d.title)[:60] + "-" + url_hash(d.source_url)[:6],
            "title": d.title,
            "summary": d.summary or d.title,
            "difficulty": d.difficulty,
            "thumbnail_url": d.thumbnail_url,
            "code_language": d.code_language if d.code_snippet else None,
            "code_snippet": d.code_snippet if d.code_license else None,
            "code_license": d.code_license if d.code_snippet else None,
            "source_type": d.source_type,
            "source_url": d.source_url,
            "source_author": d.source_author,
            "source_license": d.source_license,
            "upvotes": d.upvotes,
        }
        stmt = insert(UseCase).values(**values)
        await s.execute(
            stmt.on_conflict_do_update(
                index_elements=["component_id", "source_url"],
                set_={k: stmt.excluded[k] for k in ("title", "summary", "thumbnail_url", "upvotes")},
            )
        )
        n += 1
    return n
