"""API behaviour incl. A2 (zero-result fallback) and A3 (429 after N requests/min)."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.app.main import create_app
from api.app.security import sign_token
from api.tests.factory import seed_small
from common.models import Component
from common.settings import Settings

pytestmark = pytest.mark.db
ADMIN_TOKEN = "test-admin-token-123"
NOW = datetime.now(UTC)


def _settings(**over: object) -> Settings:
    base = {
        "env": "test",
        "admin_token_sha256": hashlib.sha256(ADMIN_TOKEN.encode()).hexdigest(),
        "api_rate_limit_per_minute": 1000,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
async def seeded(db_sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with db_sessionmaker() as s:
        data = await seed_small(s, NOW)
        await s.commit()
    return data


@pytest.fixture
async def client(seeded: dict[str, object], redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(_settings(), redis=redis)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as c:
            yield c


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    r = Redis.from_url("redis://localhost:6379/14")
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.aclose()


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.headers["x-request-id"]


async def test_component_detail_bd_user(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/components/esp32-wroom-32", headers={"CF-IPCountry": "BD", "cf-ipcity": "Dhaka"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mpn"] == "ESP32-WROOM-32" and d["offer_count"] == 3
    offers = d["offer_summary"]["offers"]
    assert offers[0]["source"]["name"] == "demo-robotics-bd"  # local + cheapest
    assert d["offer_summary"]["currency"] == "BDT"
    assert d["low_price"]["amount"] == "520.00"
    assert d["datasheets"][0]["host"] == "www.espressif.com"
    assert d["use_cases"][0]["code_license"] == "CC0-1.0"
    assert any(a["slug"] == "esp32-wroom-32d" for a in d["alternatives"])
    assert d["breadcrumbs"][-1]["path"] == "/component/esp32-wroom-32"
    assert d["faq"] and "520.00" in d["faq"][0]["answer"]
    for o in offers:
        assert o["observed_at"] and o["source"]["display_name"]  # no price without "as of" + attribution


async def test_offers_modes_and_currency(client: httpx.AsyncClient) -> None:
    r = await client.get(
        "/v1/components/esp32-wroom-32/offers",
        params={"mode": "fastest", "currency": "USD", "country": "BD", "city": "Dhaka"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["currency"] == "USD" and d["mode"] == "fastest"
    assert {o["source"]["name"] for o in d["offers"]} >= {"demo-robotics-bd", "demo-global-dist"}
    local = (
        await client.get("/v1/components/esp32-wroom-32/offers", params={"local_only": True, "country": "BD"})
    ).json()
    assert all(o["ships_from"] == "BD" for o in local["offers"])
    berlin = (
        await client.get("/v1/components/esp32-wroom-32/offers", params={"country": "DE", "city": "Berlin"})
    ).json()
    assert [o["source"]["name"] for o in berlin["offers"]] == ["demo-global-dist"]
    assert berlin["offers"][0]["sponsored"] is True


async def test_404_merged_retired(
    client: httpx.AsyncClient, db_sessionmaker: async_sessionmaker[AsyncSession], seeded: dict[str, object]
) -> None:
    assert (await client.get("/v1/components/nope-123")).status_code == 404
    async with db_sessionmaker() as s:
        d = await s.get(Component, seeded["esp_d"].id)  # type: ignore[attr-defined]
        d.status, d.merged_into = "merged", seeded["esp"].id  # type: ignore[attr-defined,union-attr]
        n = await s.get(Component, seeded["ne555"].id)  # type: ignore[attr-defined]
        n.status = "retired"  # type: ignore[union-attr]
        await s.commit()
    r = await client.get("/v1/components/esp32-wroom-32d", follow_redirects=False)
    assert r.status_code == 301 and r.json()["detail"]["redirect_to"] == "esp32-wroom-32"
    assert (await client.get("/v1/components/ne555p")).status_code == 410


async def test_search_mpn_and_natural(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/search", params={"q": "esp32-wroom-32"})
    d = r.json()
    assert r.status_code == 200 and d["kind"] == "mpn" and d["hits"][0]["slug"] == "esp32-wroom-32"
    assert d["backend"] == "postgres"
    r2 = await client.get("/v1/search", params={"q": "timer ic"})
    assert any(h["slug"] == "ne555p" for h in r2.json()["hits"])
    r3 = await client.get("/v1/search", params={"q": "esp32 wroom", "ships_to_bd": True})
    assert r3.json()["found"] >= 1 and all(h["ships_to_bd"] for h in r3.json()["hits"])


async def test_a2_zero_result_fallback(client: httpx.AsyncClient, redis: Redis) -> None:
    r = await client.get("/v1/search", params={"q": "STM32H743ZIT6"})
    assert r.status_code == 200
    d = r.json()
    assert d["found"] == 0 and d["discovery_queued"] is True and "queued" in d["message"]
    assert await redis.llen("discovery:queue") == 1
    await client.get("/v1/search", params={"q": "STM32H743ZIT6"})
    assert await redis.llen("discovery:queue") == 1  # deduplicated


async def test_a3_rate_limit(seeded: dict[str, object], redis: Redis) -> None:
    app = create_app(_settings(api_rate_limit_per_minute=5), redis=redis)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as c,
    ):
        codes = [
            (await c.get("/v1/categories", headers={"CF-Connecting-IP": "203.0.113.9"})).status_code for _ in range(7)
        ]
        other = await c.get("/v1/categories", headers={"CF-Connecting-IP": "203.0.113.10"})
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    assert other.status_code == 200


async def test_go_redirect_applies_affiliate(client: httpx.AsyncClient) -> None:
    offers = (await client.get("/v1/components/esp32-wroom-32/offers", params={"country": "DE"})).json()["offers"]
    r = await client.get(offers[0]["go_url"], follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://aff.demo-global.test/r?u=https%3A%2F%2Fshop.test")
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


async def test_alert_flow_and_account_deletion(client: httpx.AsyncClient) -> None:
    secret = _settings().secret_key.get_secret_value()
    login = sign_token(secret, {"purpose": "login", "email": "maker@example.com"}, 600)
    sess = (await client.post("/v1/alerts/session", json={"token": login})).json()["session_token"]
    h = {"Authorization": f"Bearer {sess}"}
    r = await client.post(
        "/v1/alerts", json={"component_slug": "esp32-wroom-32", "target": "500", "currency": "BDT"}, headers=h
    )
    assert r.status_code == 201, r.text
    alerts = (await client.get("/v1/alerts", headers=h)).json()
    assert alerts[0]["target"] == "500.00" and alerts[0]["armed"] is True
    assert (await client.get("/v1/alerts")).status_code == 401
    assert (await client.post("/v1/alerts/session", json={"token": sess})).status_code == 401  # wrong purpose
    assert (await client.delete("/v1/account", headers=h)).status_code == 200
    assert (await client.get("/v1/alerts", headers=h)).json() == []


async def test_opt_out_and_report(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/legal/opt-out",
        json={"domain": "demo-techshop.test", "contact_email": "owner@example.com", "reason": "Please stop listing us"},
    )
    assert r.status_code == 202
    r2 = await client.post(
        "/v1/reports", json={"component_slug": "esp32-wroom-32", "field": "price", "message": "Price is outdated"}
    )
    assert r2.status_code == 202


async def test_admin_requires_token_and_takedown(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/admin/review")).status_code == 401
    assert (await client.get("/v1/admin/review", headers={"Authorization": "Bearer wrong"})).status_code == 403
    h = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    req = (
        await client.post(
            "/v1/legal/opt-out",
            json={"domain": "demo-techshop.test", "contact_email": "o@example.com", "reason": "remove us"},
        )
    ).json()["id"]
    resp = await client.get("/v1/admin/review", params={"kind": "takedown"}, headers=h)
    items = resp.json()
    assert resp.status_code == 200, resp.text
    assert items and items[0]["ref_id"] == req
    assert (await client.post(f"/v1/admin/takedowns/{req}", json={"accept": True}, headers=h)).status_code == 200
    offers = (await client.get("/v1/components/esp32-wroom-32/offers", params={"country": "BD"})).json()["offers"]
    assert "demo-techshop-bd" not in {o["source"]["name"] for o in offers}


async def test_browse_and_sitemap(client: httpx.AsyncClient) -> None:
    cats = (await client.get("/v1/categories")).json()
    assert {"category": "wireless", "count": 2} in cats
    page = (await client.get("/v1/categories/wireless")).json()
    assert page["total"] == 2
    mfrs = (await client.get("/v1/manufacturers")).json()
    assert any(m["slug"] == "texas-instruments" for m in mfrs)
    assert (await client.get("/v1/manufacturers/espressif")).json()["total"] == 2
    sm = (await client.get("/v1/sitemap/components")).json()
    assert {e["slug"] for e in sm} == {"esp32-wroom-32", "esp32-wroom-32d", "ne555p"}
    cmp = (await client.get("/v1/compare", params={"parts": "esp32-wroom-32,esp32-wroom-32d"})).json()
    assert len(cmp["components"]) == 2 and "Flash" in cmp["spec_keys"]
