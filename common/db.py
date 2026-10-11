"""Async database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from common.settings import get_settings


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or get_settings().database_url, pool_pre_ping=True, pool_size=10)


def get_sessionmaker(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(url), expire_on_commit=False)


@asynccontextmanager
async def session_scope(url: str | None = None) -> AsyncIterator[AsyncSession]:
    """Unit of work: commits on success, rolls back on error."""
    async with get_sessionmaker(url)() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
