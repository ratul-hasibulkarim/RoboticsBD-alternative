"""C2: the per-host limiter never grants faster than the declared/crawl-delay interval."""

from __future__ import annotations

import asyncio
from crawler.fetcher.ratelimit import HostRateLimiter, effective_interval_s


def test_effective_interval_takes_slowest() -> None:
    assert effective_interval_s(0.5, None) == 2.0
    assert effective_interval_s(2.0, 3.0) == 3.0
    assert effective_interval_s(None, None) == 2.0  # default 0.5 rps
    assert effective_interval_s(1.0, 0.1) == 1.0
    assert effective_interval_s(1.0, None, robots_rps=0.2) == 5.0


async def test_never_exceeds_rate_under_concurrent_load(redis) -> None:  # type: ignore[no-untyped-def]
    limiter = HostRateLimiter(redis)
    interval = 0.2
    grants: list[float] = []

    async def worker() -> None:
        for _ in range(3):
            grants.append(await limiter.acquire("shop.test", interval))

    # 10 concurrent "workers" hammering the same host: 30 grants total.
    await asyncio.gather(*(worker() for _ in range(10)))
    grants.sort()
    gaps = [b - a for a, b in zip(grants, grants[1:], strict=False)]
    assert len(grants) == 30
    # Grant times come from the Redis server clock, so the bound is exact.
    assert min(gaps) >= interval, min(gaps)


async def test_hosts_are_independent(redis) -> None:  # type: ignore[no-untyped-def]
    limiter = HostRateLimiter(redis)
    assert await limiter.try_acquire("a.test", 10) == 0.0
    assert await limiter.try_acquire("b.test", 10) == 0.0
    assert await limiter.try_acquire("a.test", 10) > 9.0


async def test_penalize_blocks_host(redis) -> None:  # type: ignore[no-untyped-def]
    limiter = HostRateLimiter(redis)
    await limiter.penalize("shop.test", 120)
    wait = await limiter.try_acquire("shop.test", 1)
    assert 119 < wait <= 120


async def test_acquire_times_out(redis) -> None:  # type: ignore[no-untyped-def]
    limiter = HostRateLimiter(redis)
    await limiter.penalize("shop.test", 1000)
    try:
        await limiter.acquire("shop.test", 1, max_wait_s=5)
    except TimeoutError:
        return
    raise AssertionError("expected TimeoutError")
