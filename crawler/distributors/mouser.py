"""Mouser Search API (v1 JSON). https://api.mouser.com/api/docs/ui/index"""

from __future__ import annotations

import re
from typing import Any

from common.http import ApiClient
from crawler.api_gate import require_api_access
from crawler.extractors.types import ExtractedListing, PriceBreak
from crawler.normalizer.currency import parse_number
from crawler.registry import SourceConfig

BASE = "https://api.mouser.com/api/v1"


def map_part(p: dict[str, Any]) -> ExtractedListing | None:
    url = p.get("ProductDetailUrl")
    mpn = p.get("ManufacturerPartNumber")
    if not url or not mpn:
        return None
    breaks = []
    currency = None
    for b in p.get("PriceBreaks") or []:
        price = parse_number(str(b.get("Price", "")))
        qty = b.get("Quantity")
        if price is not None and isinstance(qty, int) and qty >= 1:
            breaks.append(PriceBreak(qty=qty, price=price))
            currency = currency or b.get("Currency")
    breaks.sort(key=lambda x: x.qty)
    stock_raw = str(p.get("AvailabilityInStock") or "")
    m = re.match(r"(\d+)", stock_raw.replace(",", "")) or re.match(r"(\d+)", str(p.get("Availability") or "").replace(",", ""))
    stock = int(m.group(1)) if m else None
    specs = {a["AttributeName"]: a["AttributeValue"] for a in p.get("ProductAttributes") or []
             if a.get("AttributeName") and a.get("AttributeValue") and a["AttributeName"] not in ("Packaging", "Standard Pack Qty")}
    moq = int(p["Min"]) if str(p.get("Min", "")).isdigit() else (breaks[0].qty if breaks else 1)
    return ExtractedListing(
        url=url, title=f"{mpn} {p.get('Description') or ''}".strip(), mpn=mpn, mpn_trusted=True,
        manufacturer=p.get("Manufacturer"), sku=p.get("MouserPartNumber"),
        price=breaks[0].price if breaks else None, currency=currency, price_breaks=breaks, moq=moq,
        in_stock=(stock > 0) if stock is not None else None, stock_qty=stock, condition="new",
        image_urls=[p["ImagePath"]] if p.get("ImagePath") else [], datasheet_url=p.get("DataSheetUrl") or None,
        specs=specs, category_hint=p.get("Category"), snippet=p.get("Description"),
        ships_from="US", ships_to=["*"], methods=["mouser_api"],
    )


class MouserClient:
    def __init__(self, source: SourceConfig, api_key: str, client: ApiClient | None = None) -> None:
        require_api_access(source, api_key)
        self.key = api_key
        self.client = client or ApiClient(BASE)

    async def _post(self, path: str, body: dict[str, Any]) -> list[ExtractedListing]:
        data = await self.client.post_json(f"{BASE}{path}", params={"apiKey": self.key}, json=body)
        if data.get("Errors"):
            raise RuntimeError(f"Mouser API error: {data['Errors']}")
        parts = (data.get("SearchResults") or {}).get("Parts") or []
        return [x for x in (map_part(p) for p in parts) if x is not None]

    async def by_part_number(self, mpn: str) -> list[ExtractedListing]:
        return await self._post("/search/partnumber", {"SearchByPartRequest": {"mouserPartNumber": mpn, "partSearchOptions": "Exact"}})

    async def by_keyword(self, keyword: str, records: int = 50, start: int = 0) -> list[ExtractedListing]:
        return await self._post(
            "/search/keyword", {"SearchByKeywordRequest": {"keyword": keyword, "records": records, "startingRecord": start}}
        )


