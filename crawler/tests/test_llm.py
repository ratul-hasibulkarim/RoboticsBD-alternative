"""Stage B: confidence gate, audit data, and the daily cost cap (C6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import respx

from common.http import ApiClient
from crawler.extractors.llm import BudgetGuard, LlmExtractor
from crawler.extractors.pipeline import Outcome, extract
from crawler.tests.conftest import make_source

# A product page with no structured data at all → rules fail → LLM stage runs.
UNSTRUCTURED = b"""<html><head><title>BMP280 sensor</title><meta property="og:type" content="product"></head>
<body><h1>BMP280 Barometric Pressure Sensor Module</h1><p>Price: 220 taka</p><p>I2C/SPI, 1.8-3.6V</p></body></html>"""


def _completion(confidence: float, tokens: int = 2000) -> dict[str, object]:
    content = {
        "title": "BMP280 Barometric Pressure Sensor Module", "mpn": "BMP280", "manufacturer": "Bosch",
        "price": 220, "currency": "BDT", "moq": None, "in_stock": None, "stock_qty": None,
        "ships_from": None, "ships_to": [], "specs": {"Interface": "I2C/SPI", "Supply voltage": "1.8-3.6V"},
        "price_breaks": [], "use_case_snippets": ["Weather stations and altimeters."], "confidence": confidence,
    }
    return {"choices": [{"message": {"content": json.dumps(content)}}], "usage": {"total_tokens": tokens}}


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 11, 23, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _llm(redis, clock: Clock, budget_usd: float = 0.01) -> LlmExtractor:  # type: ignore[no-untyped-def]
    guard = BudgetGuard(redis, budget_usd, clock=clock)
    # $0.003 / 1k tokens → 2000 tokens cost $0.006 per call
    return LlmExtractor(ApiClient("https://llm.test"), guard, model="test", cost_per_1k_tokens_usd=0.003)


@respx.mock
async def test_high_confidence_is_committed(redis) -> None:  # type: ignore[no-untyped-def]
    respx.post("https://llm.test/v1/chat/completions").respond(200, json=_completion(0.93))
    res = await extract(UNSTRUCTURED, "https://shop.test/bmp280", make_source(), llm=_llm(redis, Clock()))
    assert res.outcome is Outcome.OK_LLM
    assert res.listing is not None and res.listing.mpn == "BMP280"
    assert res.llm is not None and res.llm.cost_micros == 6000 and res.llm.input_hash


@respx.mock
async def test_low_confidence_goes_to_review(redis) -> None:  # type: ignore[no-untyped-def]
    respx.post("https://llm.test/v1/chat/completions").respond(200, json=_completion(0.6))
    res = await extract(UNSTRUCTURED, "https://shop.test/bmp280", make_source(), llm=_llm(redis, Clock()))
    assert res.outcome is Outcome.REVIEW
    assert not res.committable


@respx.mock
async def test_budget_pauses_then_resumes_next_day(redis) -> None:  # type: ignore[no-untyped-def]
    """C6: stage B pauses at the daily budget and resumes after UTC midnight."""
    route = respx.post("https://llm.test/v1/chat/completions").respond(200, json=_completion(0.95))
    clock = Clock()
    llm = _llm(redis, clock, budget_usd=0.01)
    src = make_source()
    first = await extract(UNSTRUCTURED, "https://shop.test/a", src, llm=llm)  # spends 0.006
    second = await extract(UNSTRUCTURED, "https://shop.test/b", src, llm=llm)  # 0.006 < 0.01 → runs, now 0.012
    third = await extract(UNSTRUCTURED, "https://shop.test/c", src, llm=llm)  # over budget → paused
    assert [first.outcome, second.outcome, third.outcome] == [Outcome.OK_LLM, Outcome.OK_LLM, Outcome.LLM_PAUSED]
    assert route.call_count == 2
    clock.now += timedelta(hours=2)  # next UTC day
    fourth = await extract(UNSTRUCTURED, "https://shop.test/c", src, llm=llm)
    assert fourth.outcome is Outcome.OK_LLM
    assert route.call_count == 3


async def test_rules_continue_when_llm_paused(redis) -> None:  # type: ignore[no-untyped-def]
    clock = Clock()
    llm = _llm(redis, clock, budget_usd=0.0)
    page = b"""<script type="application/ld+json">{"@type":"Product","name":"NE555P","offers":{"price":"10","priceCurrency":"BDT"}}</script>"""
    res = await extract(page, "https://shop.test/ne555", make_source(), llm=llm)
    assert res.outcome is Outcome.OK


async def test_no_llm_configured(redis) -> None:  # type: ignore[no-untyped-def]
    res = await extract(UNSTRUCTURED, "https://shop.test/bmp280", make_source(), llm=None)
    assert res.outcome is Outcome.LLM_DISABLED
