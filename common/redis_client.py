"""Shared async Redis connection."""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from common.settings import get_settings


@lru_cache(maxsize=2)
def get_redis(url: str | None = None) -> Redis:
    return Redis.from_url(url or get_settings().redis_url, decode_responses=False)
