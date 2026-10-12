"""GET /v1/search — Typesense with Postgres fallback, 5-minute Redis cache."""

from __future__ import annotations

import dataclasses
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from api.app.deps import GeoDep, RedisDep, SessionDep, SettingsDep
from api.app.security import session_hash
from search.service import PostgresBackend, SearchParams, SearchResponse, SearchService, TypesenseBackend

router = APIRouter(prefix="/v1", tags=["search"])


@router.get("/search")
async def search(
    request: Request,
    s: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    geo: GeoDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    page: Annotated[int, Query(ge=1, le=50)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 24,
    category: str | None = None,
    manufacturer: str | None = None,
    package: str | None = None,
    in_stock: bool | None = None,
    ships_to_bd: bool | None = None,
    sort: Literal["relevance", "price", "popularity"] = "relevance",
) -> dict[str, object]:
    ts = request.app.state.typesense
    primary = TypesenseBackend(ts) if ts is not None else PostgresBackend(s)
    fallback = PostgresBackend(s) if ts is not None else None
    service = SearchService(
        primary,
        fallback,
        redis,
        request.app.state.embedder,
        cache_ttl_s=settings.search_cache_ttl_s,
        session=s,
    )
    params = SearchParams(
        q=q,
        page=page,
        per_page=per_page,
        category=category,
        manufacturer=manufacturer,
        package=package,
        in_stock=in_stock,
        ships_to_bd=ships_to_bd,
        sort=sort,
        user_country=geo.country,
    )
    resp: SearchResponse = await service.search(
        params, session_hash=session_hash(settings.secret_key.get_secret_value(), request)
    )
    return dataclasses.asdict(resp)
