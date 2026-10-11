"""Use-case drafts produced by tutorial sources (YouTube, GitHub, Reddit)."""

from __future__ import annotations

from pydantic import BaseModel, Field

PERMISSIVE_LICENSES = frozenset(
    {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "CC0-1.0", "UNLICENSE", "0BSD", "ZLIB", "MPL-2.0"}
)


class UseCaseDraft(BaseModel):
    title: str = Field(max_length=200)
    summary: str = Field(max_length=600)
    source_type: str
    source_url: str
    source_author: str | None = None
    source_license: str | None = None
    thumbnail_url: str | None = None
    code_language: str | None = None
    code_snippet: str | None = Field(default=None, max_length=4000)
    code_license: str | None = None
    difficulty: str | None = None
    upvotes: int = 0


def clip(text: str | None, n: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"
