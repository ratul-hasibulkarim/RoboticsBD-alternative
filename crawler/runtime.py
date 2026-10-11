"""Builds production collaborators (DB, Redis, fetcher, LLM) from Settings."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.http import ApiClient
from common.settings import Settings, get_settings
from crawler.extractors.llm import BudgetGuard, LlmExtractor
from crawler.fetcher.client import build_crawler_client
from crawler.fetcher.ratelimit import HostRateLimiter
from crawler.fetcher.robots import RobotsCache
from crawler.fetcher.stores import FilesystemRawStore, PgPageStore, PgSourceStateStore, RawStore, S3RawStore
from crawler.fetcher.worker import Fetcher


@dataclass
class Runtime:
    settings: Settings
    sm: async_sessionmaker[AsyncSession]
    redis: Redis
    fetcher: Fetcher
    raw: RawStore
    llm: LlmExtractor | None


def build_raw_store(settings: Settings) -> RawStore:
    if settings.env != "test":
        return S3RawStore(
            settings.s3_endpoint,
            settings.s3_bucket_raw,
            settings.s3_access_key.get_secret_value(),
            settings.s3_secret_key.get_secret_value(),
        )
    return FilesystemRawStore(Path(".raw"))


@asynccontextmanager
async def runtime(settings: Settings | None = None, *, raw: RawStore | None = None) -> AsyncIterator[Runtime]:
    settings = settings or get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url)
    client = build_crawler_client()
    raw_store = raw or build_raw_store(settings)
    fetcher = Fetcher(
        client=client,
        robots=RobotsCache(redis, client),
        limiter=HostRateLimiter(redis),
        pages=PgPageStore(sm),
        source_state=PgSourceStateStore(sm, redis),
        raw=raw_store,
    )
    llm_client = None
    llm = None
    if settings.llm_base_url:
        llm_client = ApiClient(settings.llm_base_url)
        llm = LlmExtractor(
            llm_client,
            BudgetGuard(redis, settings.llm_daily_budget_usd),
            model=settings.llm_model,
            cost_per_1k_tokens_usd=settings.llm_cost_per_1k_tokens_usd,
            api_key=settings.llm_api_key.get_secret_value(),
        )
    try:
        yield Runtime(settings, sm, redis, fetcher, raw_store, llm)
    finally:
        await client.aclose()
        if llm_client is not None:
            await llm_client.aclose()
        await redis.aclose()
        await engine.dispose()
