"""Celery tasks — one queue per pipeline stage (spec v1.1 §0 row 18: Celery on Redis only).

  crawl.seed → crawl.fetch → (extract inline) → crawl.resolve → search.index
  maintenance: fx refresh, alerts, retention, raw purge, deferred resolution, recrawl scheduling

Each task is a thin sync wrapper around an async function in crawler/ops.py & friends.
The legal gate is enforced again here: tasks look sources up via approved_sources().
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any, TypeVar

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from common.settings import get_settings
from common.timeutil import utcnow

T = TypeVar("T")

settings = get_settings()
app = Celery("voltfind", broker=settings.celery_broker_url)
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="crawl.fetch",
    task_routes={
        "crawler.tasks.seed_source": {"queue": "crawl.seed"},
        "crawler.tasks.seed_all": {"queue": "crawl.seed"},
        "crawler.tasks.fetch_url": {"queue": "crawl.fetch"},
        "crawler.tasks.resolve": {"queue": "crawl.resolve"},
        "crawler.tasks.index_component": {"queue": "search.index"},
        "crawler.tasks.*": {"queue": "maintenance"},
    },
    beat_schedule={
        "seed-all-daily": {"task": "crawler.tasks.seed_all", "schedule": crontab(minute=7, hour=1)},
        "schedule-due-recrawls": {"task": "crawler.tasks.schedule_due", "schedule": 600.0},
        "fx-refresh": {"task": "crawler.tasks.fx_refresh", "schedule": crontab(minute=13, hour="*/6")},
        "price-alerts": {"task": "crawler.tasks.run_alerts", "schedule": 900.0},
        "retention": {"task": "crawler.tasks.retention", "schedule": crontab(minute=29, hour=3)},
        "purge-raw": {"task": "crawler.tasks.purge_raw", "schedule": crontab(minute=41, hour=3)},
        "resolve-deferred": {"task": "crawler.tasks.resolve_deferred", "schedule": 3600.0},
    },
)


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _source(name: str):  # type: ignore[no-untyped-def]
    from crawler.registry import approved_sources

    for s in approved_sources():
        if s.name == name:
            return s
    return None  # not approved (or removed) → tasks become no-ops


@app.task(name="crawler.tasks.seed_all")
def seed_all() -> int:
    from crawler.registry import approved_sources

    n = 0
    for s in approved_sources():
        if s.type == "crawl":
            seed_source.delay(s.name)
            n += 1
    return n


@app.task(name="crawler.tasks.seed_source")
def seed_source(name: str) -> int:
    src = _source(name)
    if src is None:
        return 0

    async def go() -> int:
        from crawler.ops import source_db_id
        from crawler.runtime import runtime
        from crawler.seeds.sitemap import walk_category, walk_sitemaps

        count = 0
        async with runtime() as rt:
            async with rt.sm() as s:
                sid = await source_db_id(s, name)
            sitemaps = [str(x.url) for x in src.seeds if x.kind == "sitemap" and x.url]
            categories = [str(x.url) for x in src.seeds if x.kind == "category" and x.url]
            if sitemaps:
                async for url in walk_sitemaps(rt.fetcher, src, sid, sitemaps):
                    fetch_url.delay(name, url)
                    count += 1
            for cat in categories:
                async for url in walk_category(rt.fetcher, src, sid, cat):
                    fetch_url.delay(name, url)
                    count += 1
        return count

    return run(go())


@app.task(name="crawler.tasks.fetch_url", bind=True, max_retries=5)
def fetch_url(self: Any, name: str, url: str) -> str:
    src = _source(name)
    if src is None:
        return "not_approved"

    async def go() -> tuple[str, str | None, float | None]:
        from crawler.ops import fetch_and_extract
        from crawler.runtime import runtime
        from price.fx import load_table

        async with runtime() as rt:
            async with rt.sm() as s:
                fx = await load_table(s)
            r = await fetch_and_extract(rt.sm, rt.fetcher, src, url, fx, llm=rt.llm, llm_model=rt.settings.llm_model)
            return str(r.outcome or r.fetch_status), str(r.listing_id) if r.listing_id else None, r.retry_after_s

    status, listing_id, retry_after = run(go())
    if status == "retry_later":
        raise self.retry(countdown=int(retry_after or 600))
    if status == "llm_paused":
        raise self.retry(countdown=6 * 3600)  # budget resets at UTC midnight
    if listing_id:
        resolve.delay(listing_id, False)
    return status


@app.task(name="crawler.tasks.resolve")
def resolve(listing_id: str, allow_untrusted_create: bool) -> str:
    async def go() -> tuple[str, str | None]:
        from crawler.ops import resolve_listing
        from crawler.runtime import runtime
        from resolver.embedder import get_embedder

        async with runtime() as rt, rt.sm() as s:
            action, cid = await resolve_listing(
                s, uuid.UUID(listing_id), get_embedder(), allow_untrusted_create=allow_untrusted_create
            )
            await s.commit()
            if action.value == "defer":
                await rt.redis.zadd("resolver:deferred", {listing_id: utcnow().timestamp() + 24 * 3600})
            return action.value, str(cid) if cid else None

    action, cid = run(go())
    if cid:
        index_component.delay(cid)
    return action


@app.task(name="crawler.tasks.resolve_deferred")
def resolve_deferred() -> int:
    async def go() -> list[str]:
        from crawler.runtime import runtime

        async with runtime() as rt:
            now = utcnow().timestamp()
            due = await rt.redis.zrangebyscore("resolver:deferred", 0, now, start=0, num=1000)
            if due:
                await rt.redis.zrem("resolver:deferred", *due)
            return [d.decode() for d in due]

    ids = run(go())
    for lid in ids:
        resolve.delay(lid, True)
    return len(ids)


@app.task(name="crawler.tasks.index_component")
def index_component(component_id: str) -> bool:
    async def go() -> bool:
        from crawler.runtime import runtime
        from search.indexer import index_components, typesense_client

        async with runtime() as rt, rt.sm() as s:
            n = await index_components(s, typesense_client(rt.settings), [uuid.UUID(component_id)])
            await revalidate_component(s, uuid.UUID(component_id))
            return n == 1

    return run(go())


async def revalidate_component(s: Any, component_id: uuid.UUID) -> None:
    """On-demand ISR (§10.1): tell Next.js the component page changed."""
    from common.http import ApiClient
    from common.models import Component

    slug = (await s.execute(select(Component.slug).where(Component.id == component_id))).scalar_one_or_none()
    if slug is None:
        return
    st = get_settings()
    async with ApiClient() as c:
        try:
            await c.request(
                "POST",
                st.web_revalidate_url,
                json={"paths": [f"/component/{slug}", f"/component/{slug}/prices"]},
                headers={"x-revalidate-secret": st.web_revalidate_secret.get_secret_value()},
            )
        except Exception:  # the page revalidates hourly anyway (revalidate: 3600)
            return


@app.task(name="crawler.tasks.schedule_due")
def schedule_due(limit: int = 2000) -> int:
    """Enqueue listings whose recrawl interval elapsed (reads the crawl_priority view)."""

    async def go() -> list[tuple[str, str]]:
        from sqlalchemy import text

        from crawler.runtime import runtime

        async with runtime() as rt, rt.sm() as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT s.name, cp.url FROM crawl_priority cp JOIN sources s ON s.id = cp.source_id "
                        "WHERE cp.next_due <= now() ORDER BY cp.next_due LIMIT :limit"
                    ),
                    {"limit": limit},
                )
            ).all()
            return [(r[0], r[1]) for r in rows]

    due = run(go())
    for name, url in due:
        fetch_url.delay(name, url)
    return len(due)


@app.task(name="crawler.tasks.fx_refresh")
def fx_refresh() -> int:
    async def go() -> int:
        from common.http import ApiClient
        from crawler.runtime import runtime
        from price.fx import fetch_rates, store_rates

        async with runtime() as rt, ApiClient() as c, rt.sm() as s:
            rates = await fetch_rates(c, rt.settings.fx_provider_url)
            n = await store_rates(s, utcnow().date(), rates, rt.settings.fx_provider_url)
            await s.commit()
            return n

    return run(go())


@app.task(name="crawler.tasks.run_alerts")
def run_alerts() -> dict[str, int]:
    async def go() -> dict[str, int]:
        from crawler.runtime import runtime
        from price.alerts import SmtpNotifier, evaluate_alerts
        from price.fx import load_table

        async with runtime() as rt, rt.sm() as s:
            st = rt.settings
            notifier = SmtpNotifier(
                st.smtp_host, st.smtp_port, st.smtp_sender, st.smtp_username,
                st.smtp_password.get_secret_value(), st.public_site_url,
            )
            counts = await evaluate_alerts(s, await load_table(s), utcnow(), notifier)
            await s.commit()
            return counts

    return run(go())


@app.task(name="crawler.tasks.retention")
def retention() -> tuple[int, int]:
    async def go() -> tuple[int, int]:
        from crawler.runtime import runtime
        from price.snapshotter import apply_retention

        async with runtime() as rt, rt.sm() as s:
            out = await apply_retention(s, utcnow())
            await s.commit()
            return out

    return run(go())


@app.task(name="crawler.tasks.purge_raw")
def purge_raw() -> int:
    async def go() -> int:
        from crawler.ops import purge_expired_raw
        from crawler.runtime import runtime

        async with runtime() as rt, rt.sm() as s:
            n = await purge_expired_raw(s, rt.raw.delete)
            await s.commit()
            return n

    return run(go())
