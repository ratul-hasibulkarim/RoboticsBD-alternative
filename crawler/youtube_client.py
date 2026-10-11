"""YouTube Data API v3 — metadata only (title, description excerpt, thumbnail, channel). No transcripts."""

from __future__ import annotations

from common.http import ApiClient
from crawler.api_gate import require_api_access
from crawler.content_types import UseCaseDraft, clip
from crawler.registry import SourceConfig

BASE = "https://www.googleapis.com/youtube/v3"
QUERY_TEMPLATES = ("{mpn} tutorial", "{mpn} arduino")


class YouTubeClient:
    def __init__(self, source: SourceConfig, api_key: str, client: ApiClient | None = None) -> None:
        require_api_access(source, api_key)
        self.key = api_key
        self.client = client or ApiClient(BASE)

    async def tutorials(self, mpn: str, per_query: int = 5) -> list[UseCaseDraft]:
        """search.list costs 100 quota units per call; 2 queries per part."""
        seen: set[str] = set()
        out: list[UseCaseDraft] = []
        for tpl in QUERY_TEMPLATES:
            data = await self.client.get_json(
                f"{BASE}/search",
                params={"part": "snippet", "q": tpl.format(mpn=mpn), "type": "video", "maxResults": per_query,
                        "relevanceLanguage": "en", "safeSearch": "strict", "key": self.key},
            )
            for item in data.get("items") or []:
                vid = (item.get("id") or {}).get("videoId")
                sn = item.get("snippet") or {}
                if not vid or vid in seen:
                    continue
                if mpn.lower().replace("-", "") not in (sn.get("title", "") + sn.get("description", "")).lower().replace("-", ""):
                    continue  # only videos that actually mention the part
                seen.add(vid)
                thumbs = sn.get("thumbnails") or {}
                thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
                out.append(UseCaseDraft(
                    title=clip(sn.get("title"), 200), summary=clip(sn.get("description") or sn.get("title"), 600),
                    source_type="youtube", source_url=f"https://www.youtube.com/watch?v={vid}",
                    source_author=sn.get("channelTitle"), source_license="YouTube Standard License (linked, not copied)",
                    thumbnail_url=thumb,
                ))
        return out
