"""FastAPI gateway: auth, per-IP rate limit, security headers, routing (§3)."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.app.routers import admin, alerts, components, go, legal, search
from api.app.security import RateLimiter, client_ip
from common.settings import Settings, get_settings
from resolver.embedder import get_embedder


def create_app(settings: Settings | None = None, *, typesense: Any = None, redis: Redis | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=20, max_overflow=10)
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.redis = redis or Redis.from_url(settings.redis_url)
        app.state.ratelimiter = RateLimiter(app.state.redis, settings.api_rate_limit_per_minute)
        app.state.fx_cache = {}
        app.state.embedder = get_embedder()
        ts = typesense
        if ts is None and settings.env != "test":
            from search.indexer import typesense_client

            ts = typesense_client(settings)
        app.state.typesense = ts
        try:
            yield
        finally:
            if ts is not None and typesense is None:
                await ts.aclose()
            if redis is None:
                await app.state.redis.aclose()
            await engine.dispose()

    app = FastAPI(
        title="VoltFind API",
        version="1.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_site_url],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["authorization", "content-type"],
    )

    @app.middleware("http")
    async def gateway(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        t0 = time.perf_counter()
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        path = request.url.path
        if path not in ("/healthz",) and not path.startswith("/v1/admin"):
            rl = await request.app.state.ratelimiter.hit(client_ip(request))
            if not rl.allowed:
                return JSONResponse(
                    {"detail": "rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(rl.reset_s), "X-RateLimit-Limit": str(settings.api_rate_limit_per_minute),
                             "X-RateLimit-Remaining": "0", "X-Request-ID": request_id},
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - t0) * 1000:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if path.startswith(("/v1/admin", "/v1/alerts", "/v1/account")):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException) -> JSONResponse:
        headers = dict(exc.headers or {})
        if exc.status_code == 301 and isinstance(exc.detail, dict) and exc.detail.get("redirect_to"):
            headers["Location"] = f"/v1/components/{exc.detail['redirect_to']}"
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    for r in (components.router, search.router, alerts.router, legal.router, go.router, admin.router):
        app.include_router(r)
    return app


app = create_app()
