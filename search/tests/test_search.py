from __future__ import annotations

import json

import httpx
import respx

from search.indexer import SCHEMA, SYNONYMS
from search.query_understanding import QueryKind, parse_query
from search.service import SearchParams, SearchService, TypesenseBackend
from search.typesense import TypesenseClient


def test_schema_dims_match_embedder() -> None:
    emb = next(f for f in SCHEMA["fields"] if f["name"] == "embedding")
    assert emb["num_dim"] == 384
    assert "esp32" in SYNONYMS


def test_query_understanding() -> None:
    assert parse_query("LM2596S-ADJ").kind is QueryKind.MPN
    assert parse_query("lm2596s-adj").mpn_key == "lm2596sadj"
    q = parse_query("ultrasonic sensor")
    assert q.kind is QueryKind.CATEGORY and q.category == "sensor"
    n = parse_query("cheapest esp32 board in dhaka under 800 tk")
    assert n.kind is QueryKind.NATURAL and n.wants_bd and n.max_price_usd_minor == int(800 / 122 * 100)
    assert parse_query("how to use 74HC595 with arduino").mpn == "74HC595"


def test_typesense_request_has_geo_boost_and_hybrid() -> None:
    backend = TypesenseBackend(TypesenseClient("http://ts:8108", "k"))
    pq = parse_query("wifi module for iot")
    req = backend.build_request(SearchParams(q=pq.raw, user_country="BD", in_stock=True), pq, [0.1] * 384)
    assert req["sort_by"].startswith("_text_match:desc,ships_to_bd:desc")
    assert req["vector_query"].startswith("embedding:([") and "alpha:0.3" in req["vector_query"]
    assert "in_stock:=true" in req["filter_by"]
    mpn_req = backend.build_request(SearchParams(q="ESP32-WROOM-32"), parse_query("ESP32-WROOM-32"), None)
    assert mpn_req["q"] == "esp32wroom32" and "vector_query" not in mpn_req


@respx.mock
async def test_typesense_backend_parses_hits_and_facets() -> None:
    respx.post("http://ts:8108/multi_search").respond(
        200,
        json={
            "results": [
                {
                    "found": 1,
                    "hits": [
                        {
                            "document": {
                                "id": "1",
                                "slug": "esp32-wroom-32",
                                "mpn": "ESP32-WROOM-32",
                                "title": "ESP32",
                                "category": "wireless",
                                "offer_count": 3,
                                "in_stock": True,
                                "ships_to_bd": True,
                                "lowest_price_usd_minor": 426,
                            }
                        }
                    ],
                    "facet_counts": [{"field_name": "manufacturer", "counts": [{"value": "Espressif", "count": 1}]}],
                }
            ]
        },
    )
    svc = SearchService(TypesenseBackend(TypesenseClient("http://ts:8108", "k")), None, None, None)
    resp = await svc.search(SearchParams(q="esp32-wroom-32"))
    assert resp.found == 1 and resp.hits[0].lowest_price_usd_minor == 426
    assert resp.facets["manufacturer"] == [("Espressif", 1)]
    body = json.loads(respx.calls.last.request.content)
    assert body["searches"][0]["collection"] == "components"


@respx.mock
async def test_typesense_down_uses_fallback() -> None:
    respx.post("http://ts:8108/multi_search").mock(side_effect=httpx.ConnectError("down"))

    class Fallback:
        name = "postgres"
        calls = 0

        async def search(self, p, pq, emb):  # type: ignore[no-untyped-def]
            from search.service import SearchResponse

            Fallback.calls += 1
            return SearchResponse(pq.raw, pq.kind.value, [], 0, 1, 24, {}, "postgres")

    from common.http import ApiClient

    async def no_sleep(_: float) -> None:
        return None

    ts = TypesenseClient("http://ts:8108", "k", api=ApiClient("http://ts:8108", max_retries=0, sleep=no_sleep))
    svc = SearchService(TypesenseBackend(ts), Fallback(), None, None)
    resp = await svc.search(SearchParams(q="nothing"))
    assert resp.backend == "postgres" and Fallback.calls == 1
