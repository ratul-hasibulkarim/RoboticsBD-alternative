"""SQLAlchemy 2.0 ORM mapping of api/alembic/versions/0001_init.py.

The migration is the source of truth; `tests/python/test_models_match_db.py` fails
if a mapped column is missing from the database.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBED_DIM = 384


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012 — SQLAlchemy reads this class attribute
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text)
    rate_limit_rps: Mapped[Decimal] = mapped_column(Numeric, server_default="0.5")
    robots_url: Mapped[str | None] = mapped_column(Text)
    robots_checked_at: Mapped[datetime | None]
    robots_hash: Mapped[str | None] = mapped_column(Text)
    legal_review_status: Mapped[str] = mapped_column(Text, server_default="pending")
    legal_reviewed_by: Mapped[str | None] = mapped_column(Text)
    legal_reviewed_at: Mapped[datetime | None]
    tos_url: Mapped[str | None] = mapped_column(Text)
    api_key_ref: Mapped[str | None] = mapped_column(Text)
    crawl_status: Mapped[str] = mapped_column(Text, server_default="ok")
    crawl_status_reason: Mapped[str | None] = mapped_column(Text)
    crawl_status_at: Mapped[datetime | None]
    extractor: Mapped[str] = mapped_column(Text, server_default="generic")
    js_required: Mapped[bool] = mapped_column(Boolean, server_default="false")
    cache_ttl_hours: Mapped[int] = mapped_column(Integer, server_default="48")
    trust_score: Mapped[Decimal] = mapped_column(Numeric, server_default="0.5")
    affiliate_template: Mapped[str | None] = mapped_column(Text)
    warehouse_country: Mapped[str | None] = mapped_column(Text)
    warehouse_city: Mapped[str | None] = mapped_column(Text)
    warehouse_lat: Mapped[float | None] = mapped_column(Float)
    warehouse_lon: Mapped[float | None] = mapped_column(Float)
    ships_to: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Image(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"))
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    s3_key: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    phash: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text, server_default="source-hosted")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Component(Base):
    __tablename__ = "components"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    mpn: Mapped[str] = mapped_column(Text)
    mpn_norm: Mapped[str] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    manufacturer_norm: Mapped[str] = mapped_column(Text, server_default="")
    gtin: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    subcategory: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    short_desc: Mapped[str | None] = mapped_column(Text)
    long_desc: Mapped[str | None] = mapped_column(Text)
    prose_md: Mapped[str | None] = mapped_column(Text)
    prose_reviewed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    specs_norm: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    package: Mapped[str | None] = mapped_column(Text)
    lifecycle: Mapped[str] = mapped_column(Text, server_default="unknown")
    primary_image: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("images.id"))
    datasheet_url: Mapped[str | None] = mapped_column(Text)
    datasheet_host: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    popularity: Mapped[float] = mapped_column(Float, server_default="0")
    status: Mapped[str] = mapped_column(Text, server_default="active")
    merged_into: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ComponentImage(Base):
    __tablename__ = "component_images"

    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"), primary_key=True)
    image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("images.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, server_default="0")


class CrawlPage(Base):
    __tablename__ = "crawl_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(Text, unique=True)
    final_url: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime]
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    raw_ref: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(Text, unique=True)
    source_sku: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    raw_title: Mapped[str] = mapped_column(Text)
    raw_mpn: Mapped[str | None] = mapped_column(Text)
    mpn_trusted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    raw_manufacturer: Mapped[str | None] = mapped_column(Text)
    package: Mapped[str | None] = mapped_column(Text)
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    image_url: Mapped[str | None] = mapped_column(Text)
    datasheet_url: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    match_method: Mapped[str | None] = mapped_column(Text)
    condition: Mapped[str] = mapped_column(Text, server_default="new")
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    stock_qty: Mapped[int | None] = mapped_column(Integer)
    ships_from: Mapped[str | None] = mapped_column(Text)
    ships_to: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    extraction_method: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default="0")
    first_seen: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(server_default=func.now())
    last_attempt: Mapped[datetime | None]
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    # Hypertable without a PK; map (time, listing_id) as the ORM identity.
    time: Mapped[datetime] = mapped_column(primary_key=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(Text)
    price_minor: Mapped[int] = mapped_column(BigInteger)
    price_breaks: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    moq: Mapped[int] = mapped_column(Integer, server_default="1")
    shipping_minor: Mapped[int | None] = mapped_column(BigInteger)
    tax_included: Mapped[bool | None] = mapped_column(Boolean)
    observed_at: Mapped[datetime]


class PriceCurrent(Base):
    __tablename__ = "price_current"

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(Text)
    price_minor: Mapped[int] = mapped_column(BigInteger)
    price_breaks: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    moq: Mapped[int] = mapped_column(Integer, server_default="1")
    shipping_minor: Mapped[int | None] = mapped_column(BigInteger)
    price_usd_minor: Mapped[int] = mapped_column(BigInteger)
    landed_usd_minor: Mapped[int] = mapped_column(BigInteger)
    observed_at: Mapped[datetime]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PriceDaily(Base):
    __tablename__ = "price_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(Text)
    min_minor: Mapped[int] = mapped_column(BigInteger)
    max_minor: Mapped[int] = mapped_column(BigInteger)
    close_minor: Mapped[int] = mapped_column(BigInteger)
    usd_min_minor: Mapped[int] = mapped_column(BigInteger)


class FxRate(Base):
    __tablename__ = "fx_rates"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(Text, primary_key=True)
    per_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    source: Mapped[str] = mapped_column(Text)


class UseCase(Base):
    __tablename__ = "use_cases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"))
    slug: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    steps: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    wiring_diagram: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("images.id"))
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    code_language: Mapped[str | None] = mapped_column(Text)
    code_snippet: Mapped[str | None] = mapped_column(Text)
    code_license: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_author: Mapped[str | None] = mapped_column(Text)
    source_license: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    upvotes: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Datasheet(Base):
    __tablename__ = "datasheets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"))
    url: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text)
    revision: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default="false")
    checked_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ShipEstimate(Base):
    __tablename__ = "ship_estimates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    from_country: Mapped[str] = mapped_column(Text)
    to_country: Mapped[str] = mapped_column(Text)
    to_city: Mapped[str] = mapped_column(Text, server_default="")
    cost_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text)
    eta_days_min: Mapped[int] = mapped_column(Integer)
    eta_days_max: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(Text, server_default="standard")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Query(Base):
    __tablename__ = "queries"
    time: Mapped[datetime] = mapped_column(primary_key=True)
    query_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    result_count: Mapped[int | None] = mapped_column(Integer)
    clicked_listing: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_country: Mapped[str | None] = mapped_column(Text)
    session_hash: Mapped[str | None] = mapped_column(Text)


class ComponentViewsDaily(Base):
    __tablename__ = "component_views_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"), primary_key=True)
    views: Mapped[int] = mapped_column(Integer, server_default="0")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"))
    target_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, server_default="1")
    ship_to: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    armed: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_fired_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MergeAudit(Base):
    __tablename__ = "merge_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    action: Mapped[str] = mapped_column(Text)
    listing_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    from_component: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_component: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    method: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


class ReviewItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    ref_id: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
    resolved_by: Mapped[str | None] = mapped_column(Text)


class LlmExtractionLog(Base):
    __tablename__ = "llm_extraction_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    cost_usd_micros: Mapped[int] = mapped_column(BigInteger, server_default="0")
    committed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    error: Mapped[str | None] = mapped_column(Text)


class TakedownRequest(Base):
    __tablename__ = "takedown_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain: Mapped[str] = mapped_column(Text)
    contact_email: Mapped[str] = mapped_column(CITEXT)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]


class DataReport(Base):
    __tablename__ = "data_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id"))
    field: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Guide(Base):
    __tablename__ = "guides"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    body_md: Mapped[str] = mapped_column(Text)
    query_cluster: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
