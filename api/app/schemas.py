"""Pydantic v2 request/response models for the public and admin API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Money(BaseModel):
    amount: Decimal
    currency: str
    usd_minor: int


class SourceRef(BaseModel):
    name: str
    display_name: str
    domain: str
    trust_score: float


class OfferOut(BaseModel):
    listing_id: uuid.UUID
    source: SourceRef
    url: str
    go_url: str  # our click-out redirect (/go/{listing_id})
    sponsored: bool  # affiliate link → rel="sponsored"
    title: str
    condition: str
    in_stock: bool | None
    stock_qty: int | None
    moq: int
    quantity: int
    unit_price: Money
    landed_total: Money
    landed_per_unit: Money
    shipping: Money
    duty_estimate: Money
    eta_days: float
    distance_km: float | None
    ships_from: str | None
    observed_at: datetime
    freshness: Literal["fresh", "recent", "stale"]
    score: float


class OffersOut(BaseModel):
    component_slug: str
    mode: str
    quantity: int
    currency: str
    country: str
    city: str | None
    local_only: bool
    offers: list[OfferOut]
    total: int
    fx_day: date


class ImageOut(BaseModel):
    url: str
    width: int | None
    height: int | None
    attribution: str
    license: str


class DatasheetOut(BaseModel):
    url: str
    host: str
    revision: str | None
    page_count: int | None
    language: str | None
    is_primary: bool
    checked_at: datetime


class UseCaseOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    difficulty: str | None
    summary: str
    steps: list[str]
    thumbnail_url: str | None
    code_language: str | None
    code_snippet: str | None
    code_license: str | None
    source_type: str
    source_url: str
    source_author: str | None
    source_license: str | None
    upvotes: int


class ComponentCard(BaseModel):
    slug: str
    mpn: str
    title: str
    manufacturer: str | None
    category: str
    subcategory: str | None
    package: str | None
    image_url: str | None
    lowest_price_usd_minor: int | None
    offer_count: int


class HistoryPoint(BaseModel):
    day: date
    min_usd_minor: int


class FaqItem(BaseModel):
    question: str
    answer: str


class Breadcrumb(BaseModel):
    name: str
    path: str


class ComponentDetail(BaseModel):
    id: uuid.UUID
    slug: str
    mpn: str
    title: str
    manufacturer: str | None
    category: str
    subcategory: str | None
    package: str | None
    lifecycle: str
    short_desc: str | None
    prose_md: str | None
    prose_reviewed: bool
    specs: dict[str, str]
    images: list[ImageOut]
    datasheets: list[DatasheetOut]
    use_cases: list[UseCaseOut]
    alternatives: list[ComponentCard]
    related: list[ComponentCard]
    history: list[HistoryPoint]
    offer_summary: OffersOut
    low_price: Money | None
    high_price: Money | None
    offer_count: int
    faq: list[FaqItem]
    breadcrumbs: list[Breadcrumb]
    updated_at: datetime


class GoneOut(BaseModel):
    status: Literal["merged", "retired"]
    redirect_to: str | None


class CategoryOut(BaseModel):
    category: str
    count: int


class ManufacturerOut(BaseModel):
    manufacturer: str
    slug: str
    count: int


class PagedComponents(BaseModel):
    items: list[ComponentCard]
    total: int
    page: int
    per_page: int


class SitemapEntry(BaseModel):
    slug: str
    updated_at: datetime
    image_url: str | None


class CompareOut(BaseModel):
    components: list[ComponentDetail]
    spec_keys: list[str]


# ------------------------------------------------------------------ write models


class MagicLinkRequest(BaseModel):
    email: EmailStr


class SessionRequest(BaseModel):
    token: str


class SessionOut(BaseModel):
    session_token: str
    email: str


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_slug: str
    target: Decimal = Field(gt=0)
    currency: Literal["BDT", "USD", "EUR"]
    quantity: int = Field(default=1, ge=1, le=100_000)
    ship_to: str = Field(default="BD", min_length=2, max_length=2)


class AlertOut(BaseModel):
    id: uuid.UUID
    component_slug: str
    component_title: str
    target: Decimal
    currency: str
    quantity: int
    ship_to: str
    active: bool
    armed: bool
    last_fired_at: datetime | None


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_slug: str | None = None
    listing_id: uuid.UUID | None = None
    field: Literal["price", "stock", "specs", "datasheet", "image", "match", "other"]
    message: str = Field(min_length=5, max_length=2000)


class OptOutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str = Field(min_length=3, max_length=253, pattern=r"^[a-z0-9.-]+\.[a-z]{2,}$")
    contact_email: EmailStr
    reason: str = Field(min_length=5, max_length=2000)


class NotifyCreate(BaseModel):
    email: EmailStr
    q: str = Field(min_length=1, max_length=200)


class Accepted(BaseModel):
    ok: bool = True
    id: str | None = None


# ------------------------------------------------------------------ admin models


class ReviewItemOut(BaseModel):
    id: int
    kind: str
    ref_id: str
    reason: str
    payload: dict[str, object]
    status: str
    created_at: datetime


class ReviewResolve(BaseModel):
    component_id: uuid.UUID | None = None


class MergeRequest(BaseModel):
    keep: uuid.UUID
    drop: uuid.UUID
    force: bool = False


class SplitRequest(BaseModel):
    listing_ids: list[uuid.UUID] = Field(min_length=1)
    new_mpn: str = Field(min_length=2)
    new_manufacturer: str | None = None


class ComponentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    category: str | None = None
    subcategory: str | None = None
    short_desc: str | None = None
    prose_md: str | None = Field(default=None, max_length=4000)
    prose_reviewed: bool | None = None
    lifecycle: Literal["active", "nrnd", "obsolete", "unknown"] | None = None
    status: Literal["active", "retired"] | None = None


class SourceOut(BaseModel):
    name: str
    display_name: str
    type: str
    legal_review_status: str
    crawl_status: str
    crawl_status_reason: str | None
    active: bool


class CrawlStatusUpdate(BaseModel):
    status: Literal["ok", "review_required", "failing", "disabled"]
    reason: str = Field(min_length=3, max_length=500)


class TakedownDecision(BaseModel):
    accept: bool


class GuidePublish(BaseModel):
    reviewer: str = Field(min_length=2)
