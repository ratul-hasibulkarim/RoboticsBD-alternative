"""Per-host rate limiter shared by every fetcher process.

Implemented as GCRA (generic cell rate algorithm, burst = 1) in a Redis Lua script,
using the Redis server clock so that workers on different machines agree. With
burst 1 this guarantees consecutive grants for a host are at least `interval`
apart — the strict reading of "never more than 1 request per Crawl-delay".
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis

DEFAULT_RPS = 0.5

# KEYS[1] = host key; ARGV[1] = interval in microseconds; ARGV[2] = 1 to reserve, 0 to peek
# Returns {microseconds to wait (0 = granted now), server time in microseconds}.
_GCRA_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000000 + tonumber(t[2])
local interval = tonumber(ARGV[1])
local tat = tonumber(redis.call('GET', KEYS[1]) or '0')
if tat > now then
  return {tat - now, now}
end
if ARGV[2] == '1' then
  redis.call('SET', KEYS[1], tostring(now + interval), 'PX', math.ceil(interval / 1000) + 1000)
end
return {0, now}
"""

# KEYS[1] = host key; ARGV[1] = penalty microseconds. Pushes the next allowed time forward.
_PENALIZE_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000000 + tonumber(t[2])
local tat = tonumber(redis.call('GET', KEYS[1]) or '0')
local until_ = now + tonumber(ARGV[1])
if until_ > tat then
  redis.call('SET', KEYS[1], tostring(until_), 'PX', math.ceil(tonumber(ARGV[1]) / 1000) + 1000)
end
return until_
"""


def effective_interval_s(
    declared_rps: float | None, crawl_delay_s: float | None, robots_rps: float | None = None
) -> float:
    """The slowest of: our declared limit, robots Crawl-delay, robots Request-rate."""
    rps = declared_rps if declared_rps and declared_rps > 0 else DEFAULT_RPS
    interval = 1.0 / rps
    if crawl_delay_s is not None and crawl_delay_s > interval:
        interval = crawl_delay_s
    if robots_rps is not None and robots_rps > 0 and 1.0 / robots_rps > interval:
        interval = 1.0 / robots_rps
    return interval


class HostRateLimiter:
    def __init__(
        self,
        redis: Redis,
        *,
        prefix: str = "rl:host:",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.redis = redis
        self.prefix = prefix
        self._sleep = sleep
        self._gcra = redis.register_script(_GCRA_LUA)
        self._penalize = redis.register_script(_PENALIZE_LUA)

    async def _try(self, host: str, interval_s: float) -> tuple[float, float]:
        wait_us, now_us = await self._gcra(keys=[self.prefix + host], args=[int(interval_s * 1_000_000), 1])
        return int(wait_us) / 1_000_000, int(now_us) / 1_000_000

    async def try_acquire(self, host: str, interval_s: float) -> float:
        """Reserve a slot if free. Returns seconds to wait (0.0 = granted)."""
        return (await self._try(host, interval_s))[0]

    async def acquire(self, host: str, interval_s: float, *, max_wait_s: float = 300.0) -> float:
        """Block until a slot for `host` is granted, or raise TimeoutError.

        Returns the grant time (Redis server clock, epoch seconds).
        """
        waited = 0.0
        while True:
            wait, now = await self._try(host, interval_s)
            if wait == 0.0:
                return now
            if waited + wait > max_wait_s:
                raise TimeoutError(f"rate limit wait for {host} exceeds {max_wait_s}s")
            await self._sleep(wait)
            waited += wait

    async def penalize(self, host: str, seconds: float) -> None:
        """Block the host for all workers (Retry-After, 503, ...)."""
        await self._penalize(keys=[self.prefix + host], args=[int(seconds * 1_000_000)])
