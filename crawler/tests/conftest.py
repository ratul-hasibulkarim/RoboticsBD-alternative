from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
from redis.asyncio import Redis

from crawler.fetcher.stores import PageRecord, PreviousFetch
from crawler.registry import SourceConfig

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    r = Redis.from_url(TEST_REDIS_URL)
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.aclose()


class MemoryPageStore:
    def __init__(self) -> None:
        self.rows: dict[str, PageRecord] = {}
        self.history: list[PageRecord] = []

    async def previous(self, url_hash: str) -> PreviousFetch | None:
        r = self.rows.get(url_hash)
        if r is None:
            return None
        return PreviousFetch(r.etag, r.last_modified, r.content_hash)

    async def record(self, page: PageRecord) -> None:
        self.history.append(page)
        old = self.rows.get(page.url_hash)
        if page.content_hash is None and old is not None:
            return  # mirrors PgPageStore: metadata-only writes keep validators/content
        self.rows[page.url_hash] = page


class MemorySourceState:
    def __init__(self) -> None:
        self.status: dict[uuid.UUID, str] = {}
        self.reasons: list[str] = []

    async def crawl_status(self, source_id: uuid.UUID) -> str:
        return self.status.get(source_id, "ok")

    async def flag(self, source_id: uuid.UUID, status: str, reason: str) -> None:
        self.status[source_id] = status
        self.reasons.append(reason)


class MemoryRawStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, body: bytes, content_type: str) -> str:
        self.objects[key] = body
        return key

    async def get(self, ref: str) -> bytes:
        return self.objects[ref]

    async def delete(self, ref: str) -> None:
        self.objects.pop(ref, None)


def make_source(**overrides: object) -> SourceConfig:
    data: dict[str, object] = {
        "name": "testshop",
        "display_name": "Test Shop",
        "domain": "shop.test",
        "type": "crawl",
        "method": "test",
        "country": "BD",
        "currency": "BDT",
        "base_url": "https://shop.test",
        "rate_limit_rps": 10.0,
        "robots_url": "https://shop.test/robots.txt",
        "robots_checked_at": None,
        "extractor": "generic",
        "seeds": [],
        "js_required": False,
        "cache_ttl_hours": 48,
        "trust_score": 0.8,
        "affiliate_template": None,
        "warehouse": None,
        "ships_to": ["BD"],
        "legal_review": {
            "status": "approved",
            "tos_url": None,
            "reviewed_by": "tester",
            "reviewed_at": date(2026, 1, 1),
            "notes": None,
        },
        "active": True,
    }
    data.update(overrides)
    return SourceConfig.model_validate(data)
