"""Repo-wide pytest fixtures: a migrated test database and per-test clean tables."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://voltfind:voltfind@localhost:5432/voltfind_test"
)
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("REDIS_URL", os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"))
os.environ.setdefault("ENV", "test")

TABLES = (
    "guides, data_reports, takedown_requests, llm_extraction_log, review_queue, merge_audit, "
    "price_alerts, users, component_views_daily, queries, ship_estimates, datasheets, use_cases, "
    "fx_rates, price_daily, price_current, price_snapshots, listings, crawl_pages, component_images, "
    "components, images, sources"
)


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "api" / "alembic.ini"), "downgrade", "base"],
        check=True,
        env=env,
        cwd=ROOT,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "api" / "alembic.ini"), "upgrade", "head"],
        check=True,
        env=env,
        cwd=ROOT,
        capture_output=True,
    )
    yield TEST_DATABASE_URL


@pytest.fixture
async def db_sessionmaker(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db, pool_size=5)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(db_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with db_sessionmaker() as s:
        yield s
