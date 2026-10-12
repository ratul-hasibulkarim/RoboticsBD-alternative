"""Official-API clients: legal/credential gate, request shape, mapping to our models."""

from __future__ import annotations

import base64
from decimal import Decimal

import pytest
import respx

from crawler.api_gate import MissingCredentialsError
from crawler.distributors.digikey import DigiKeyClient
from crawler.distributors.mouser import MouserClient
from crawler.github_client import GitHubClient
from crawler.reddit_client import RedditClient
from crawler.registry import NotApprovedError
from crawler.tests.conftest import make_source
from crawler.youtube_client import YouTubeClient


def api_source(name: str, **kw: object):  # type: ignore[no-untyped-def]
    return make_source(name=name, type="api", robots_url=None, **kw)


def test_gate_requires_approval_and_keys() -> None:
    with pytest.raises(NotApprovedError):
        MouserClient(api_source("mouser", legal_review={"status": "pending"}), "key")
    with pytest.raises(MissingCredentialsError):
        MouserClient(api_source("mouser"), "")
    with pytest.raises(NotApprovedError):
        RedditClient(api_source("reddit", legal_review={"status": "pending"}), "id", "secret")


@respx.mock
async def test_mouser_mapping() -> None:
    route = respx.post("https://api.mouser.com/api/v1/search/partnumber").respond(
        200,
        json={
            "Errors": [],
            "SearchResults": {
                "Parts": [
                    {
                        "ManufacturerPartNumber": "NE555P",
                        "Manufacturer": "Texas Instruments",
                        "MouserPartNumber": "595-NE555P",
                        "Description": "Timers & Support Products Single Precision",
                        "ProductDetailUrl": "https://www.mouser.com/ProductDetail/595-NE555P",
                        "DataSheetUrl": "https://www.ti.com/lit/ds/symlink/ne555.pdf",
                        "ImagePath": "https://www.mouser.com/images/ti/ne555.jpg",
                        "Availability": "48,211 In Stock",
                        "AvailabilityInStock": "48211",
                        "Min": "1",
                        "Category": "Timers",
                        "PriceBreaks": [
                            {"Quantity": 10, "Price": "$0.355", "Currency": "USD"},
                            {"Quantity": 1, "Price": "$0.48", "Currency": "USD"},
                        ],
                        "ProductAttributes": [{"AttributeName": "Packaging", "AttributeValue": "Tube"}],
                    }
                ]
            },
        },
    )
    res = await MouserClient(api_source("mouser"), "k").by_part_number("NE555P")
    assert route.calls.last.request.url.params["apiKey"] == "k"
    [x] = res
    assert x.mpn == "NE555P" and x.mpn_trusted and x.price == Decimal("0.48") and x.currency == "USD"
    assert [b.qty for b in x.price_breaks] == [1, 10] and x.stock_qty == 48211 and x.specs == {}
    assert x.methods == ["mouser_api"]


@respx.mock
async def test_digikey_oauth_and_mapping() -> None:
    tok = respx.post("https://api.digikey.com/v1/oauth2/token").respond(
        200, json={"access_token": "T", "expires_in": 600}
    )
    search = respx.post("https://api.digikey.com/products/v4/search/keyword").respond(
        200,
        json={
            "Products": [
                {
                    "ManufacturerProductNumber": "NE555P",
                    "Manufacturer": {"Name": "Texas Instruments"},
                    "Description": {"ProductDescription": "IC OSC SINGLE TIMER 100KHZ 8-DIP"},
                    "ProductUrl": "https://www.digikey.com/p/ne555p",
                    "DatasheetUrl": "https://www.ti.com/lit/ds/symlink/ne555.pdf",
                    "PhotoUrl": "https://mm.digikey.com/ne555p.jpg",
                    "QuantityAvailable": 120000,
                    "UnitPrice": 0.48,
                    "Parameters": [
                        {"ParameterText": "Package / Case", "ValueText": '8-DIP (0.300", 7.62mm)'},
                        {"ParameterText": "Series", "ValueText": "-"},
                    ],
                    "Category": {"Name": "Clock/Timing"},
                    "ProductVariations": [
                        {
                            "DigiKeyProductNumber": "296-1411-5-ND",
                            "MinimumOrderQuantity": 1,
                            "StandardPricing": [
                                {"BreakQuantity": 1, "UnitPrice": 0.48},
                                {"BreakQuantity": 10, "UnitPrice": 0.355},
                            ],
                        },
                        {"DigiKeyProductNumber": "296-NE555P-TR", "MinimumOrderQuantity": 2000, "StandardPricing": []},
                    ],
                }
            ]
        },
    )
    c = DigiKeyClient(api_source("digikey"), "id", "secret")
    [x] = await c.by_keyword("NE555P")
    await c.by_keyword("NE555P")
    assert tok.call_count == 1  # token cached
    assert search.calls.last.request.headers["authorization"] == "Bearer T"
    assert x.sku == "296-1411-5-ND" and x.package == '8-DIP (0.300", 7.62mm)' and "Series" not in x.specs
    assert x.price_breaks[1].price == Decimal("0.355")


@respx.mock
async def test_youtube_only_relevant_videos_no_transcripts() -> None:
    respx.get("https://www.googleapis.com/youtube/v3/search").respond(
        200,
        json={
            "items": [
                {
                    "id": {"videoId": "a1"},
                    "snippet": {
                        "title": "74HC595 shift register tutorial",
                        "description": "Wiring the 74HC595",
                        "channelTitle": "Maker Ch",
                        "thumbnails": {"high": {"url": "https://i.ytimg.com/vi/a1/hq.jpg"}},
                    },
                },
                {"id": {"videoId": "b2"}, "snippet": {"title": "Unrelated vlog", "description": "travel"}},
            ]
        },
    )
    drafts = await YouTubeClient(api_source("youtube"), "k").tutorials("74HC595")
    assert [d.source_url for d in drafts] == ["https://www.youtube.com/watch?v=a1"]
    assert drafts[0].code_snippet is None and drafts[0].thumbnail_url


@respx.mock
async def test_github_code_only_with_permissive_license() -> None:
    readme = "# LED matrix\n\nUses the 74HC595.\n\n```cpp\nvoid setup(){ pinMode(8, OUTPUT); }\nvoid loop(){}\n```\n"
    respx.get("https://api.github.com/search/repositories").respond(
        200,
        json={
            "items": [
                {
                    "full_name": "a/mit",
                    "name": "mit",
                    "html_url": "https://github.com/a/mit",
                    "license": {"spdx_id": "MIT"},
                    "owner": {"login": "a"},
                    "stargazers_count": 40,
                    "description": "595 demo",
                },
                {
                    "full_name": "b/gpl",
                    "name": "gpl",
                    "html_url": "https://github.com/b/gpl",
                    "license": {"spdx_id": "GPL-3.0"},
                    "owner": {"login": "b"},
                    "stargazers_count": 10,
                    "description": "595 demo",
                },
            ]
        },
    )
    content = base64.b64encode(readme.encode()).decode()
    respx.get("https://api.github.com/repos/a/mit/readme").respond(200, json={"content": content})
    respx.get("https://api.github.com/repos/b/gpl/readme").respond(200, json={"content": content})
    mit, gpl = await GitHubClient(api_source("github"), "t").projects("74HC595")
    assert mit.code_snippet and mit.code_license == "MIT" and mit.code_language == "arduino"
    assert gpl.code_snippet is None and gpl.code_license is None
    assert "```" not in mit.summary and len(mit.summary) <= 600
