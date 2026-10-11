"""Rate limiting, admin auth, magic-link tokens and anonymised session hashes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from common.settings import Settings
from common.timeutil import utcnow

MAGIC_LINK_TTL_S = 30 * 60
SESSION_TTL_S = 30 * 24 * 3600


def client_ip(request: Request) -> str:
    # Cloudflare in front (spec §3.1): trust CF-Connecting-IP, else the direct peer.
    ip = request.headers.get("cf-connecting-ip")
    if ip:
        return ip.strip()
    return request.client.host if request.client else "unknown"


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_s: int


class RateLimiter:
    """Fixed one-minute window per IP (A3). Atomic INCR + EXPIRE in a pipeline."""

    def __init__(self, redis: Redis, per_minute: int, prefix: str = "rl:api:") -> None:
        self.redis = redis
        self.per_minute = per_minute
        self.prefix = prefix

    async def hit(self, key: str) -> RateLimitResult:
        window = int(time.time() // 60)
        k = f"{self.prefix}{key}:{window}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(k)
            pipe.expire(k, 61)
            count, _ = await pipe.execute()
        reset = 60 - int(time.time() % 60)
        return RateLimitResult(int(count) <= self.per_minute, max(0, self.per_minute - int(count)), reset)


def require_admin(request: Request, settings: Settings) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "admin token required")
    token = auth[7:].strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    allowed = settings.admin_token_hashes()
    if not allowed or not any(hmac.compare_digest(digest, h) for h in allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid admin token")
    return "admin:" + digest[:8]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_token(secret: str, payload: dict[str, object], ttl_s: int) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_s
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def verify_token(secret: str, token: str, *, purpose: str) -> dict[str, object]:
    try:
        raw, sig = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed token") from exc
    expected = _b64(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad token signature")
    body: dict[str, object] = json.loads(_unb64(raw))
    if int(body.get("exp", 0)) < time.time():  # type: ignore[call-overload]
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")
    if body.get("purpose") != purpose:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token purpose")
    return body


def session_hash(secret: str, request: Request) -> str:
    """Salted with the secret and the UTC date → rotates daily, never reversible to an IP (LEGAL §5)."""
    day = utcnow().strftime("%Y-%m-%d")
    material = f"{day}|{client_ip(request)}|{request.headers.get('user-agent', '')}"
    return hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()[:24]
