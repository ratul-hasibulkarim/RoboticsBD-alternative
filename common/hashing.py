"""Stable hashes used as keys across the pipeline."""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that never change page content; stripped before hashing.
_TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref"}
)


def canonical_url(url: str) -> str:
    """Lower-case scheme/host, drop fragment, default ports and tracking params, sort query."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_PARAMS)
    )
    path = parts.path or "/"
    return urlunsplit((scheme, host, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
