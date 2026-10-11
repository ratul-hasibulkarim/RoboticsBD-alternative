"""Reddit Data API (OAuth, application-only). Requires a COMMERCIAL agreement before approval (LEGAL §3)."""

from __future__ import annotations

import time

import httpx

from common.http import ApiClient
from crawler.api_gate import require_api_access
from crawler.content_types import UseCaseDraft, clip
from crawler.registry import SourceConfig

SUBREDDITS = ("AskElectronics", "PrintedCircuitBoard", "electronics", "embedded", "arduino", "bangladesh")


class RedditClient:
    def __init__(self, source: SourceConfig, client_id: str, client_secret: str, client: ApiClient | None = None) -> None:
        require_api_access(source, client_id, client_secret)
        self.client_id, self.client_secret = client_id, client_secret
        self.client = client or ApiClient("https://oauth.reddit.com")
        self._token: str | None = None
        self._exp = 0.0

    async def _auth(self) -> str:
        if self._token and time.time() < self._exp - 60:
            return self._token
        resp = await self.client.request(
            "POST", "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"}, auth=httpx.BasicAuth(self.client_id, self.client_secret),
        )
        resp.raise_for_status()
        data = resp.json()
        self._token, self._exp = str(data["access_token"]), time.time() + float(data.get("expires_in", 3600))
        return self._token

    async def discussions(self, mpn: str, per_sub: int = 5, min_score: int = 5) -> list[UseCaseDraft]:
        token = await self._auth()
        out: list[UseCaseDraft] = []
        for sub in SUBREDDITS:
            data = await self.client.get_json(
                f"https://oauth.reddit.com/r/{sub}/search",
                params={"q": f'"{mpn}"', "restrict_sr": "1", "sort": "top", "t": "all", "limit": per_sub},
                headers={"Authorization": f"Bearer {token}"},
            )
            for child in (data.get("data") or {}).get("children") or []:
                d = child.get("data") or {}
                if d.get("over_18") or int(d.get("score") or 0) < min_score:
                    continue
                out.append(UseCaseDraft(
                    title=clip(d.get("title"), 200), summary=clip(d.get("selftext") or d.get("title"), 600),
                    source_type="reddit", source_url=f"https://www.reddit.com{d.get('permalink', '')}",
                    source_author=f"u/{d['author']}" if d.get("author") else None,
                    source_license="Reddit User Agreement (linked, not copied)", upvotes=int(d.get("score") or 0),
                ))
        return out
