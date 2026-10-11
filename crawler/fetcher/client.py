"""The crawler's HTTP client: honest constant User-Agent, no cookies, no auth, HTTP/2."""

from __future__ import annotations

from http.cookiejar import Cookie, CookieJar
from urllib.request import Request

import httpx

from common.http import DEFAULT_TIMEOUT, USER_AGENT


class NoCookieJar(CookieJar):
    """A cookie jar that never stores anything — guarantees no session replay."""

    def set_cookie(self, cookie: Cookie) -> None:
        return None

    def extract_cookies(self, response: object, request: Request) -> None:
        return None


def build_crawler_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en,bn;q=0.8",
        },
        cookies=NoCookieJar(),
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=False,  # redirects are followed manually so each hop is robots-checked
        http2=transport is None,
        transport=transport,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
