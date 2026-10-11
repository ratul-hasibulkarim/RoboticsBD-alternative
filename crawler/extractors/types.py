"""Extraction output model shared by every extractor."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Condition = Literal["new", "used", "refurb", "unknown"]

SNIPPET_MAX = 300


class PriceBreak(BaseModel):
    model_config = ConfigDict(frozen=True)
    qty: int = Field(ge=1)
    price: Decimal = Field(ge=0)


class ExtractedListing(BaseModel):
    """Everything we may keep about one product page. Nothing else is stored."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    mpn: str | None = None
    manufacturer: str | None = None
    gtin: str | None = None
    sku: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    price_breaks: list[PriceBreak] = Field(default_factory=list)
    moq: int | None = None
    in_stock: bool | None = None
    stock_qty: int | None = None
    condition: Condition | None = None
    image_urls: list[str] = Field(default_factory=list)
    datasheet_url: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    category_hint: str | None = None
    package: str | None = None
    snippet: str | None = None
    ships_from: str | None = None
    ships_to: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    confidence: float = 1.0

    @field_validator("snippet")
    @classmethod
    def _clip_snippet(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())
        return v[: SNIPPET_MAX - 1] + "…" if len(v) > SNIPPET_MAX else v

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @property
    def is_offer(self) -> bool:
        """Minimum for a priced listing: a title and a price in a known currency."""
        return bool(self.title) and self.price is not None and bool(self.currency)

    def merge_missing(self, other: ExtractedListing) -> ExtractedListing:
        """Fill fields that are empty here from `other` (lower-priority extractor)."""
        data = self.model_dump()
        for key, value in other.model_dump().items():
            if key in ("url", "confidence"):
                continue
            if key == "methods":
                continue
            if key == "specs":
                merged = dict(value)
                merged.update(data["specs"])
                data["specs"] = merged
                continue
            if data.get(key) in (None, [], {}, "") and value not in (None, [], {}, ""):
                data[key] = value
        data["methods"] = list(dict.fromkeys([*self.methods, *other.methods]))
        return ExtractedListing.model_validate(data)
