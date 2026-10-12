#!/usr/bin/env python3
"""Export real API responses (seeded test DB) to web/tests/fixtures/api/ for the web contract
tests and the mock API used by the SSR/sitemap checks. Run after any API schema change."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://voltfind:voltfind@localhost:5432/voltfind_test")
os.environ.setdefault("ENV", "test")

import httpx  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from api.app.main import create_app  # noqa: E402
from api.tests.factory import seed_small  # noqa: E402
from common.settings import Settings  # noqa: E402
from conftest import TABLES  # noqa: E402

OUT = ROOT / "web" / "tests" / "fixtures" / "api"
GEO = "country=BD&city=Dhaka&currency=BDT"
PATHS = [
    f"/v1/components/esp32-wroom-32?{GEO}&track=false",
    f"/v1/components/esp32-wroom-32d?{GEO}&track=false",
    f"/v1/components/ne555p?{GEO}&track=false",
    f"/v1/components/esp32-wroom-32/offers?{GEO}",
    f"/v1/components/esp32-wroom-32d/offers?{GEO}",
    f"/v1/components/ne555p/offers?{GEO}",
    "/v1/components/esp32-wroom-32/use-cases",
    "/v1/components/esp32-wroom-32d/use-cases",
    "/v1/components/ne555p/use-cases",
    "/v1/components/esp32-wroom-32/alternatives?limit=16",
    "/v1/components/esp32-wroom-32d/alternatives?limit=16",
    "/v1/components/ne555p/alternatives?limit=16",
    "/v1/categories",
    "/v1/categories/wireless?page=1&per_page=24",
    "/v1/categories/ic-analog?page=1&per_page=24",
    "/v1/categories/wireless?page=1&per_page=24&ships_to_bd=true",
    "/v1/categories/ic-analog?page=1&per_page=24&ships_to_bd=true",
    "/v1/manufacturers",
    "/v1/manufacturers/espressif?page=1&per_page=24",
    "/v1/manufacturers/texas-instruments?page=1&per_page=24",
    "/v1/trending?limit=12",
    "/v1/sitemap/components?page=1",
    "/v1/sitemap/count",
    "/v1/sitemap/retired",
    "/v1/search?q=esp32&country=BD&city=Dhaka",
    "/v1/search?q=STM32H743ZIT6&country=BD&city=Dhaka",
    "/v1/compare?parts=esp32-wroom-32,esp32-wroom-32d",
]


def fixture_name(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:16] + ".json"


async def main() -> None:
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await seed_small(s, datetime.now(UTC))
        await s.commit()
    await engine.dispose()

    redis = Redis.from_url("redis://localhost:6379/13")
    await redis.flushdb()
    app = create_app(Settings(env="test", api_rate_limit_per_minute=10_000), redis=redis)
    OUT.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict[str, object]] = {}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as c,
    ):
        for path in PATHS:
            r = await c.get(path)
            name = fixture_name(path)
            (OUT / name).write_text(json.dumps(r.json(), indent=1, ensure_ascii=False) + "\n")
            index[path] = {"file": name, "status": r.status_code}
            print(r.status_code, path)
    (OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
