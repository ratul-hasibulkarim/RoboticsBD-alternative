"""GitHub REST API — repositories mentioning a part; README excerpt + license-gated code snippet."""

from __future__ import annotations

import base64
import re

from common.http import ApiClient
from crawler.api_gate import require_api_access
from crawler.content_types import PERMISSIVE_LICENSES, UseCaseDraft, clip
from crawler.registry import SourceConfig

BASE = "https://api.github.com"
_FENCE = re.compile(r"```(\w+)?\n(.*?)```", re.S)
_LANG = {
    "cpp": "arduino",
    "c++": "arduino",
    "ino": "arduino",
    "arduino": "arduino",
    "c": "c",
    "python": "micropython",
    "py": "micropython",
    "rust": "rust",
    "rs": "rust",
}


def strip_markdown(md: str) -> str:
    md = _FENCE.sub(" ", md)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"<[^>]+>", " ", md)
    md = re.sub(r"^[#>*\-\s]+", "", md, flags=re.M)
    return " ".join(md.split())


def first_code_block(md: str) -> tuple[str | None, str | None]:
    for m in _FENCE.finditer(md):
        lang = (m.group(1) or "").lower()
        if lang in _LANG and 20 <= len(m.group(2)) <= 4000:
            return _LANG[lang], m.group(2).rstrip()
    return None, None


class GitHubClient:
    def __init__(self, source: SourceConfig, token: str, client: ApiClient | None = None) -> None:
        require_api_access(source, token)
        self.client = client or ApiClient(
            BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def projects(self, mpn: str, limit: int = 5) -> list[UseCaseDraft]:
        data = await self.client.get_json(
            f"{BASE}/search/repositories",
            params={"q": f'"{mpn}" in:name,description,readme', "sort": "stars", "order": "desc", "per_page": limit},
        )
        out: list[UseCaseDraft] = []
        for repo in data.get("items") or []:
            if repo.get("fork") or repo.get("archived"):
                continue
            full = repo["full_name"]
            spdx = ((repo.get("license") or {}).get("spdx_id") or "").upper() or None
            readme = await self.client.get_json(f"{BASE}/repos/{full}/readme")
            md = base64.b64decode(readme.get("content", "")).decode("utf-8", errors="replace")
            lang, code = first_code_block(md)
            permissive = spdx in PERMISSIVE_LICENSES
            out.append(
                UseCaseDraft(
                    title=clip(f"{repo.get('name')}: {repo.get('description') or ''}", 200),
                    summary=clip(strip_markdown(md) or repo.get("description"), 600),
                    source_type="github",
                    source_url=repo["html_url"],
                    source_author=(repo.get("owner") or {}).get("login"),
                    source_license=spdx,
                    code_language=lang if permissive else None,
                    code_snippet=code if permissive else None,
                    code_license=spdx if permissive and code else None,
                    upvotes=int(repo.get("stargazers_count") or 0),
                )
            )
        return out
