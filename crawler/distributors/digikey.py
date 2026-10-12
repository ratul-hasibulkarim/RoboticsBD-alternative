"""DigiKey Product Information API v4 (OAuth2 client credentials)."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from common.http import ApiClient
from crawler.api_gate import require_api_access
from crawler.extractors.types import ExtractedListing, PriceBreak
from crawler.registry import SourceConfig

BASE = "https://api.digikey.com"


def map_product(p: dict[str, Any]) -> ExtractedListing | None:
    mpn = p.get("ManufacturerProductNumber")
    url = p.get("ProductUrl")
    if not mpn or not url:
        return None
    variations = p.get("ProductVariations") or []
    # Prefer cut tape / tube variations with the lowest MOQ (what a hobbyist can buy).
    variations.sort(key=lambda v: v.get("MinimumOrderQuantity") or 10**9)
    var = variations[0] if variations else {}
    breaks = sorted(
        {
            PriceBreak(qty=int(b["BreakQuantity"]), price=Decimal(str(b["UnitPrice"])))
            for b in var.get("StandardPricing") or []
            if b.get("BreakQuantity") and b.get("UnitPrice") is not None
        },
        key=lambda b: b.qty,
    )
    price = breaks[0].price if breaks else (Decimal(str(p["UnitPrice"])) if p.get("UnitPrice") else None)
    stock = p.get("QuantityAvailable")
    desc = (p.get("Description") or {}).get("ProductDescription")
    specs = {
        x["ParameterText"]: x["ValueText"]
        for x in p.get("Parameters") or []
        if x.get("ParameterText") and x.get("ValueText") and x["ValueText"] not in ("-", "")
    }
    package = specs.get("Package / Case") or specs.get("Supplier Device Package")
    return ExtractedListing(
        url=url,
        title=f"{mpn} {desc or ''}".strip(),
        mpn=mpn,
        mpn_trusted=True,
        manufacturer=(p.get("Manufacturer") or {}).get("Name"),
        sku=var.get("DigiKeyProductNumber"),
        price=price,
        currency="USD",
        price_breaks=list(breaks),
        moq=var.get("MinimumOrderQuantity") or 1,
        in_stock=(stock > 0) if isinstance(stock, int) else None,
        stock_qty=stock if isinstance(stock, int) else None,
        condition="new",
        image_urls=[p["PhotoUrl"]] if p.get("PhotoUrl") else [],
        datasheet_url=p.get("DatasheetUrl") or None,
        specs=specs,
        package=package,
        category_hint=(p.get("Category") or {}).get("Name"),
        snippet=desc,
        ships_from="US",
        ships_to=["*"],
        methods=["digikey_api"],
    )


class DigiKeyClient:
    def __init__(
        self, source: SourceConfig, client_id: str, client_secret: str, client: ApiClient | None = None
    ) -> None:
        require_api_access(source, client_id, client_secret)
        self.client_id, self.client_secret = client_id, client_secret
        self.client = client or ApiClient(BASE)
        self._token: str | None = None
        self._token_exp = 0.0

    async def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        data = await self.client.post_json(
            f"{BASE}/v1/oauth2/token",
            data={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"},
        )
        self._token = str(data["access_token"])
        self._token_exp = time.time() + float(data.get("expires_in", 600))
        return self._token

    async def by_keyword(self, keyword: str, limit: int = 25, offset: int = 0) -> list[ExtractedListing]:
        token = await self._auth()
        data = await self.client.post_json(
            f"{BASE}/products/v4/search/keyword",
            json={"Keywords": keyword, "Limit": limit, "Offset": offset},
            headers={
                "Authorization": f"Bearer {token}",
                "X-DIGIKEY-Client-Id": self.client_id,
                "X-DIGIKEY-Locale-Currency": "USD",
                "X-DIGIKEY-Locale-Site": "US",
            },
        )
        return [x for x in (map_product(p) for p in data.get("Products") or []) if x is not None]
