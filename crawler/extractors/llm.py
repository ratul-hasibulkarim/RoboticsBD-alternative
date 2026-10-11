"""Stage B — LLM extraction, used only when the rule-based stage cannot produce an offer.

* OpenAI-compatible `/v1/chat/completions` (works with Ollama, vLLM, hosted APIs) and a
  strict JSON schema response format.
* Every call is logged to `llm_extraction_log` (input hash, output, confidence, cost).
* Results with confidence < LLM_MIN_CONFIDENCE (0.85) are NOT committed; the caller
  sends them to `review_queue`.
* `BudgetGuard` caps spend per UTC day in Redis. When the cap is hit, stage B pauses
  and the rule-based stage continues; the key rolls over at midnight UTC (test C6).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from redis.asyncio import Redis

from common.http import ApiClient
from common.timeutil import utcnow
from crawler.extractors.html import HTMLParser
from crawler.extractors.types import ExtractedListing, PriceBreak

PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_listing.md"
MAX_INPUT_CHARS = 12_000

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title", "mpn", "manufacturer", "price", "currency", "moq", "in_stock", "stock_qty",
        "ships_from", "ships_to", "specs", "price_breaks", "use_case_snippets", "confidence",
    ],
    "properties": {
        "title": {"type": ["string", "null"]},
        "mpn": {"type": ["string", "null"]},
        "manufacturer": {"type": ["string", "null"]},
        "price": {"type": ["number", "null"], "minimum": 0},
        "currency": {"type": ["string", "null"], "pattern": "^[A-Z]{3}$"},
        "moq": {"type": ["integer", "null"], "minimum": 1},
        "in_stock": {"type": ["boolean", "null"]},
        "stock_qty": {"type": ["integer", "null"], "minimum": 0},
        "ships_from": {"type": ["string", "null"]},
        "ships_to": {"type": "array", "items": {"type": "string"}},
        "specs": {"type": "object", "additionalProperties": {"type": "string"}},
        "price_breaks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["qty", "price"],
                "properties": {"qty": {"type": "integer", "minimum": 1}, "price": {"type": "number", "minimum": 0}},
            },
        },
        "use_case_snippets": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 200}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


class BudgetExceededError(RuntimeError):
    pass


class BudgetGuard:
    def __init__(
        self, redis: Redis, daily_usd: float, *, clock: Callable[[], datetime] = utcnow, prefix: str = "llm:spend:"
    ) -> None:
        self.redis = redis
        self.daily_micros = int(daily_usd * 1_000_000)
        self.clock = clock
        self.prefix = prefix

    def _key(self) -> str:
        return f"{self.prefix}{self.clock():%Y-%m-%d}"

    async def spent_micros(self) -> int:
        v = await self.redis.get(self._key())
        return int(v) if v else 0

    async def available(self) -> bool:
        return await self.spent_micros() < self.daily_micros

    async def check(self) -> None:
        if not await self.available():
            raise BudgetExceededError(f"LLM daily budget reached ({self.daily_micros / 1e6:.2f} USD)")

    async def charge(self, micros: int) -> int:
        key = self._key()
        total = int(await self.redis.incrby(key, max(0, micros)))
        await self.redis.expire(key, 3 * 86400)
        return total


@dataclass(frozen=True)
class LlmResult:
    listing: ExtractedListing | None
    raw: dict[str, Any] | None
    confidence: float
    cost_micros: int
    input_hash: str
    use_case_snippets: list[str]
    error: str | None = None


def page_text(tree: HTMLParser) -> str:
    for sel in ("script", "style", "noscript", "svg", "nav", "footer", "header", "form"):
        for n in tree.css(sel):
            n.decompose()
    body = tree.body or tree.root
    text = body.text(separator="\n", strip=True) if body is not None else ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)[:MAX_INPUT_CHARS]


def _to_listing(url: str, d: dict[str, Any]) -> ExtractedListing:
    return ExtractedListing(
        url=url,
        title=d.get("title"),
        mpn=d.get("mpn"),
        manufacturer=d.get("manufacturer"),
        price=Decimal(str(d["price"])) if d.get("price") is not None else None,
        currency=d.get("currency"),
        moq=d.get("moq"),
        in_stock=d.get("in_stock"),
        stock_qty=d.get("stock_qty"),
        ships_from=d.get("ships_from"),
        ships_to=list(d.get("ships_to") or []),
        specs={str(k): str(v) for k, v in (d.get("specs") or {}).items()},
        price_breaks=[PriceBreak(qty=int(b["qty"]), price=Decimal(str(b["price"]))) for b in d.get("price_breaks") or []],
        methods=["llm"],
        confidence=float(d.get("confidence") or 0.0),
    )


class LlmExtractor:
    def __init__(
        self,
        client: ApiClient,
        guard: BudgetGuard,
        *,
        model: str,
        cost_per_1k_tokens_usd: float,
        api_key: str = "",
    ) -> None:
        self.client = client
        self.guard = guard
        self.model = model
        self.cost_per_1k = cost_per_1k_tokens_usd
        self.api_key = api_key
        self.template = PROMPT_PATH.read_text(encoding="utf-8")

    async def extract(self, tree: HTMLParser, url: str) -> LlmResult:
        text = page_text(tree)
        input_hash = hashlib.sha256(f"{url}\n{text}".encode()).hexdigest()
        await self.guard.check()  # raises BudgetExceededError → caller pauses stage B
        prompt = self.template.replace("{url}", url).replace("{text}", text)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "listing", "strict": True, "schema": OUTPUT_SCHEMA},
            },
        }
        try:
            resp = await self.client.post_json("/v1/chat/completions", json=payload, headers=headers)
        except Exception as exc:  # network / provider errors are logged, not fatal
            return LlmResult(None, None, 0.0, 0, input_hash, [], error=repr(exc))
        usage = resp.get("usage") or {}
        tokens = int(usage.get("total_tokens") or 0)
        cost_micros = int(tokens / 1000 * self.cost_per_1k * 1_000_000)
        await self.guard.charge(cost_micros)
        try:
            content = resp["choices"][0]["message"]["content"]
            data = json.loads(content)
            listing = _to_listing(url, data)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return LlmResult(None, None, 0.0, cost_micros, input_hash, [], error=f"bad output: {exc!r}")
        return LlmResult(
            listing=listing,
            raw=data,
            confidence=listing.confidence,
            cost_micros=cost_micros,
            input_hash=input_hash,
            use_case_snippets=[s[:200] for s in data.get("use_case_snippets") or []][:3],
        )
