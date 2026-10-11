"""FastAPI dependencies."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.settings import Settings, get_settings
from price.fx import FxTable, load_table
from api.app.security import require_admin
from price.geo import UserGeo, geo_from_headers, resolve_geo


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def settings_dep(request: Request) -> Settings:
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    return settings


async def get_fx(request: Request, session: Annotated[AsyncSession, Depends(get_session)]) -> FxTable:
    cache = request.app.state.fx_cache
    fx: FxTable | None = cache.get("table")
    if fx is None or cache.get("loaded_at", 0) < time.time() - 3600:
        fx = await load_table(session)
        cache["table"], cache["loaded_at"] = fx, time.time()
    return fx


def get_geo(request: Request, country: str | None = None, city: str | None = None) -> UserGeo:
    """Explicit ?country=&city= override the Cloudflare headers (user can change location)."""
    if country or city:
        return resolve_geo(country, city)
    return geo_from_headers(dict(request.headers))


def admin_actor(request: Request, settings: Annotated[Settings, Depends(settings_dep)]) -> str:
    return require_admin(request, settings)


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]
FxDep = Annotated[FxTable, Depends(get_fx)]
GeoDep = Annotated[UserGeo, Depends(get_geo)]
AdminDep = Annotated[str, Depends(admin_actor)]
