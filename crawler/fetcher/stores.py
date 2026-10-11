"""Persistence ports used by the fetcher, with Postgres / object-storage implementations.

The fetcher depends on these protocols, so the unit tests can run it against
in-memory implementations while production uses Postgres + S3/MinIO.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.models import CrawlPage, Source
from common.timeutil import utcnow

RAW_TTL = timedelta(days=30)


@dataclass(frozen=True)
class PreviousFetch:
    etag: str | None
    last_modified: str | None
    content_hash: str | None


@dataclass(frozen=True)
class PageRecord:
    url: str
    url_hash: str
    final_url: str
    source_id: uuid.UUID
    fetched_at: datetime
    http_status: int | None
    content_hash: str | None
    content_type: str | None
    etag: str | None
    last_modified: str | None
    raw_ref: str | None
    error: str | None


class PageStore(Protocol):
    async def previous(self, url_hash: str) -> PreviousFetch | None: ...
    async def record(self, page: PageRecord) -> None: ...


class SourceStateStore(Protocol):
    async def crawl_status(self, source_id: uuid.UUID) -> str: ...
    async def flag(self, source_id: uuid.UUID, status: str, reason: str) -> None: ...


class RawStore(Protocol):
    async def put(self, key: str, body: bytes, content_type: str) -> str: ...
    async def get(self, ref: str) -> bytes: ...
    async def delete(self, ref: str) -> None: ...


# --------------------------------------------------------------------- Postgres


class PgPageStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sm = sessionmaker

    async def previous(self, url_hash: str) -> PreviousFetch | None:
        async with self.sm() as s:
            row = (
                await s.execute(
                    select(CrawlPage.etag, CrawlPage.last_modified, CrawlPage.content_hash).where(
                        CrawlPage.url_hash == url_hash
                    )
                )
            ).first()
        if row is None:
            return None
        return PreviousFetch(etag=row[0], last_modified=row[1], content_hash=row[2])

    async def record(self, page: PageRecord) -> None:
        values: dict[str, Any] = {
            "url": page.url,
            "url_hash": page.url_hash,
            "final_url": page.final_url,
            "source_id": page.source_id,
            "fetched_at": page.fetched_at,
            "http_status": page.http_status,
            "error": page.error,
        }
        # Only overwrite cache validators / content when we actually received content.
        if page.content_hash is not None:
            values.update(
                content_hash=page.content_hash,
                content_type=page.content_type,
                etag=page.etag,
                last_modified=page.last_modified,
                raw_ref=page.raw_ref,
                expires_at=page.fetched_at + RAW_TTL if page.raw_ref else None,
                extracted_at=None,
            )
        stmt = insert(CrawlPage).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["url_hash"], set_={k: stmt.excluded[k] for k in values if k != "url_hash"}
        )
        async with self.sm() as s:
            await s.execute(stmt)
            await s.commit()


class PgSourceStateStore:
    """crawl_status lives in Postgres; a Redis mirror makes the flag visible to all
    workers immediately (test C3: < 1 s)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self.sm = sessionmaker
        self.redis = redis

    @staticmethod
    def _key(source_id: uuid.UUID) -> str:
        return f"source:crawl_status:{source_id}"

    async def crawl_status(self, source_id: uuid.UUID) -> str:
        cached = await self.redis.get(self._key(source_id))
        if cached is not None:
            return cached.decode() if isinstance(cached, bytes) else str(cached)
        async with self.sm() as s:
            status = (
                await s.execute(select(Source.crawl_status).where(Source.id == source_id))
            ).scalar_one_or_none()
        status = status or "disabled"
        await self.redis.set(self._key(source_id), status, ex=60)
        return status

    async def flag(self, source_id: uuid.UUID, status: str, reason: str) -> None:
        await self.redis.set(self._key(source_id), status, ex=3600)
        async with self.sm() as s:
            await s.execute(
                update(Source)
                .where(Source.id == source_id)
                .values(crawl_status=status, crawl_status_reason=reason[:500], crawl_status_at=utcnow())
            )
            await s.commit()


# ---------------------------------------------------------------- raw storage


class FilesystemRawStore:
    """Dev/test raw store. Production uses S3RawStore."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("key escapes raw store root")
        return p

    async def put(self, key: str, body: bytes, content_type: str) -> str:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, body)
        return key

    async def get(self, ref: str) -> bytes:
        return await asyncio.to_thread(self._path(ref).read_bytes)

    async def delete(self, ref: str) -> None:
        await asyncio.to_thread(self._path(ref).unlink, True)


class S3RawStore:
    """S3 / MinIO raw store. Bucket lifecycle rule (infra) also expires objects at 30 days."""

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str) -> None:
        import boto3

        self.bucket = bucket
        self._s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key
        )

    async def put(self, key: str, body: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._s3.put_object, Bucket=self.bucket, Key=key, Body=body, ContentType=content_type
        )
        return key

    async def get(self, ref: str) -> bytes:
        obj = await asyncio.to_thread(self._s3.get_object, Bucket=self.bucket, Key=ref)
        body: bytes = await asyncio.to_thread(obj["Body"].read)
        return body

    async def delete(self, ref: str) -> None:
        await asyncio.to_thread(self._s3.delete_object, Bucket=self.bucket, Key=ref)


def raw_key(source_name: str, url_hash: str, fetched_at: datetime) -> str:
    return f"{source_name}/{fetched_at:%Y/%m/%d}/{url_hash}.html"
