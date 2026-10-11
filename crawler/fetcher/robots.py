"""robots.txt cache — protego parser, Redis-backed, 24 h TTL, FAIL CLOSED.

RFC 9309 behaviour:
  * 2xx            → parse and obey.
  * 4xx (not 429)  → no robots file: everything allowed (§2.3.1.3 "unavailable").
  * 5xx, 429, network error, timeout → "unreachable": everything DISALLOWED (§2.3.1.4).
    Unreachable results are cached for 1 h only so the host is retried sooner.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from protego import Protego
from redis.asyncio import Redis

from common.http import DEFAULT_TIMEOUT, USER_AGENT

ROBOTS_AGENT = "VoltFindBot"
ROBOTS_TTL_S = 24 * 3600
UNREACHABLE_TTL_S = 3600
MAX_ROBOTS_BYTES = 512 * 1024
MAX_REDIRECTS = 5


@dataclass(frozen=True)
class RobotsRules:
    origin: str
    state: str  # "parsed" | "missing" | "unreachable"
    body: str
    fetched_status: int | None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(f"{self.state}\n{self.body}".encode()).hexdigest()

    def _parser(self) -> Protego | None:
        if self.state != "parsed":
            return None
        return Protego.parse(self.body)

    def can_fetch(self, url: str) -> bool:
        if self.state == "unreachable":
            return False
        if self.state == "missing":
            return True
        parser = self._parser()
        assert parser is not None
        return bool(parser.can_fetch(url, ROBOTS_AGENT))

    def crawl_delay(self) -> float | None:
        parser = self._parser()
        if parser is None:
            return None
        delay = parser.crawl_delay(ROBOTS_AGENT)
        if delay is None:
            return None
        return float(delay)

    def request_rate_rps(self) -> float | None:
        parser = self._parser()
        if parser is None:
            return None
        rate = parser.request_rate(ROBOTS_AGENT)
        if rate is None or rate.seconds == 0:
            return None
        return float(rate.requests) / float(rate.seconds)

    def sitemaps(self) -> list[str]:
        parser = self._parser()
        return list(parser.sitemaps) if parser is not None else []

    def to_json(self) -> bytes:
        return json.dumps(
            {"origin": self.origin, "state": self.state, "body": self.body, "status": self.fetched_status}
        ).encode()

    @classmethod
    def from_json(cls, raw: bytes) -> RobotsRules:
        d = json.loads(raw)
        return cls(origin=d["origin"], state=d["state"], body=d["body"], fetched_status=d["status"])


def origin_of(url: str) -> str:
    p = urlsplit(url)
    if not p.scheme or not p.hostname:
        raise ValueError(f"not an absolute URL: {url!r}")
    host = p.hostname.lower()
    default = {"http": 80, "https": 443}.get(p.scheme)
    port = f":{p.port}" if p.port and p.port != default else ""
    return f"{p.scheme}://{host}{port}"


async def fetch_robots(client: httpx.AsyncClient, origin: str) -> RobotsRules:
    url = f"{origin}/robots.txt"
    try:
        for _ in range(MAX_REDIRECTS + 1):
            resp = await client.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT, follow_redirects=False
            )
            if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                url = str(resp.url.join(resp.headers["location"]))
                continue
            break
        else:
            return RobotsRules(origin, "unreachable", "", None)
    except (httpx.TransportError, httpx.TimeoutException):
        return RobotsRules(origin, "unreachable", "", None)

    status = resp.status_code
    if 200 <= status < 300:
        body = resp.content[:MAX_ROBOTS_BYTES].decode("utf-8", errors="replace")
        return RobotsRules(origin, "parsed", body, status)
    if 400 <= status < 500 and status != 429:
        return RobotsRules(origin, "missing", "", status)
    return RobotsRules(origin, "unreachable", "", status)


class RobotsCache:
    def __init__(self, redis: Redis, client: httpx.AsyncClient, *, prefix: str = "robots:") -> None:
        self.redis = redis
        self.client = client
        self.prefix = prefix

    async def get(self, url: str, *, force_refresh: bool = False) -> RobotsRules:
        origin = origin_of(url)
        key = self.prefix + origin
        if not force_refresh:
            cached = await self.redis.get(key)
            if cached is not None:
                return RobotsRules.from_json(cached)
        rules = await fetch_robots(self.client, origin)
        ttl = UNREACHABLE_TTL_S if rules.state == "unreachable" else ROBOTS_TTL_S
        await self.redis.set(key, rules.to_json(), ex=ttl)
        return rules

    async def can_fetch(self, url: str) -> bool:
        return (await self.get(url)).can_fetch(url)
