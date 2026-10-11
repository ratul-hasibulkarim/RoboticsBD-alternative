"""Source registry: loads crawler/sources.yaml, validates it, and is the legal gate.

`approved_sources()` is the only way the scheduler obtains sources to crawl.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import Source
from common.settings import get_settings

LegalStatus = Literal["approved", "pending", "blocked"]
SourceType = Literal["api", "crawl", "manual", "feed"]


class NotApprovedError(PermissionError):
    """Raised when code tries to use a source that has not passed legal review."""


class Warehouse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(min_length=2, max_length=2)
    city: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["sitemap", "category", "api"]
    url: HttpUrl | None = None
    params: dict[str, str] = Field(default_factory=dict)


class LegalReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: LegalStatus
    tos_url: HttpUrl | None = None
    reviewed_by: str | None = None
    reviewed_at: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _approval_needs_reviewer(self) -> LegalReview:
        if self.status == "approved" and (not self.reviewed_by or not self.reviewed_at):
            raise ValueError("approved sources must record reviewed_by and reviewed_at")
        return self


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str
    domain: str
    type: SourceType
    method: str
    country: str | None
    currency: str | None
    base_url: HttpUrl
    rate_limit_rps: float = Field(ge=0, le=10)
    robots_url: HttpUrl | None
    robots_checked_at: datetime | None
    extractor: str
    seeds: list[Seed]
    js_required: bool = False
    cache_ttl_hours: int = Field(ge=0)
    trust_score: float = Field(ge=0, le=1)
    affiliate_template: str | None
    warehouse: Warehouse | None
    ships_to: list[str]
    legal_review: LegalReview
    active: bool

    @field_validator("affiliate_template")
    @classmethod
    def _template_has_url(cls, v: str | None) -> str | None:
        if v is not None and "{url}" not in v:
            raise ValueError("affiliate_template must contain {url}")
        return v

    @model_validator(mode="after")
    def _crawl_needs_robots(self) -> SourceConfig:
        if self.type == "crawl" and self.robots_url is None:
            raise ValueError(f"{self.name}: crawl sources must declare robots_url")
        return self

    @property
    def is_approved(self) -> bool:
        return self.active and self.legal_review.status == "approved"

    def require_approved(self) -> None:
        if not self.is_approved:
            raise NotApprovedError(
                f"source {self.name!r} is not approved "
                f"(status={self.legal_review.status}, active={self.active})"
            )


class Registry(BaseModel):
    version: int
    sources: list[SourceConfig]

    @model_validator(mode="after")
    def _unique_names(self) -> Registry:
        names = [s.name for s in self.sources]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate source names: {sorted(dupes)}")
        return self

    def get(self, name: str) -> SourceConfig:
        for s in self.sources:
            if s.name == name:
                return s
        raise KeyError(name)

    def approved(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.is_approved]

    def for_host(self, host: str) -> SourceConfig | None:
        host = host.lower().removeprefix("www.")
        for s in self.sources:
            d = s.domain.lower().removeprefix("www.")
            if host == d or host.endswith("." + d):
                return s
        return None


def load_registry(path: Path | None = None) -> Registry:
    path = path or get_settings().sources_file
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Registry.model_validate(raw)


def approved_sources(path: Path | None = None) -> list[SourceConfig]:
    """The ONLY entry point the scheduler uses to choose what to crawl."""
    return load_registry(path).approved()


async def sync_sources_to_db(session: AsyncSession, registry: Registry) -> int:
    """Upsert registry rows into `sources`. Legal status in YAML always wins.

    crawl_status is NOT overwritten here; it is runtime state owned by the fetcher.
    """
    count = 0
    for s in registry.sources:
        wh = s.warehouse
        values = {
            "name": s.name,
            "display_name": s.display_name,
            "domain": s.domain,
            "type": s.type,
            "method": s.method,
            "country": s.country,
            "currency": s.currency,
            "base_url": str(s.base_url),
            "rate_limit_rps": s.rate_limit_rps,
            "robots_url": str(s.robots_url) if s.robots_url else None,
            "legal_review_status": s.legal_review.status,
            "legal_reviewed_by": s.legal_review.reviewed_by,
            "legal_reviewed_at": (
                datetime.combine(s.legal_review.reviewed_at, datetime.min.time())
                if s.legal_review.reviewed_at
                else None
            ),
            "tos_url": str(s.legal_review.tos_url) if s.legal_review.tos_url else None,
            "extractor": s.extractor,
            "js_required": s.js_required,
            "cache_ttl_hours": s.cache_ttl_hours,
            "trust_score": s.trust_score,
            "affiliate_template": s.affiliate_template,
            "warehouse_country": wh.country if wh else None,
            "warehouse_city": wh.city if wh else None,
            "warehouse_lat": wh.lat if wh else None,
            "warehouse_lon": wh.lon if wh else None,
            "ships_to": s.ships_to,
            "active": s.active,
        }
        stmt = insert(Source).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != "name"}
        await session.execute(stmt.on_conflict_do_update(index_elements=["name"], set_=update_cols))
        count += 1
    return count


async def db_source_by_name(session: AsyncSession, name: str) -> Source | None:
    return (await session.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
