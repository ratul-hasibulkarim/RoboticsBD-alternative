# VoltFind

A search engine for electronic components: one canonical page per part, prices from
Bangladeshi shops and global distributors ranked by **landed cost to your door**,
datasheet links, and tutorials. VoltFind never sells anything — every fact links to its source.

> Spec: [docs/SPEC.md](docs/SPEC.md) (v1.1 — lists every change from the original brief and why).
> Legal guardrails: [docs/LEGAL.md](docs/LEGAL.md). **No source is approved yet** — see "Going live".

## What's here

| Area | Path | Notes |
|---|---|---|
| Source registry / legal gate | `crawler/sources.yaml`, `crawler/registry.py` | Nothing is fetched unless `legal_review.status: approved` |
| Polite fetcher | `crawler/fetcher/` | robots.txt (fail closed), Redis rate limiter, conditional GET, Retry-After, 403/451 stop |
| Extraction | `crawler/extractors/` | JSON-LD → microdata → OpenGraph → WooCommerce/OpenCart/Shopify; LLM fallback with daily budget |
| Official APIs | `crawler/distributors/`, `crawler/{youtube,github,reddit}_client.py` | Mouser, DigiKey, YouTube, GitHub, Reddit (gated) |
| Entity resolution | `resolver/` | GTIN → MPN cascade, guards, merge/split audit |
| Price engine | `price/` | FX, duty estimate, ranker (best / cheapest / fastest), history, alerts |
| Search | `search/` | Typesense hybrid search + Postgres fallback |
| API | `api/` | FastAPI + Alembic |
| Website | `web/` | Next.js 15 (App Router, ISR), JSON-LD, sitemaps |
| Ads | `ads/placement_policy.yaml`, `web/components/ads/AdSlot.tsx` | AdSense, ≤ 3 slots, never above the fold |

## Run it

```bash
cp .env.example .env
make demo          # docker compose up + migrations + 500 demo parts
open http://localhost:3000
```

The demo uses **real part numbers with synthetic prices** from four clearly labelled
"Demo …" sources (`*.test` domains). It is for trying the product, not market data.

Without Docker (Postgres 16 + pgvector, Redis 7 running locally):

```bash
make install migrate
python scripts/seed_demo_data.py --components 500
uvicorn api.app.main:app --reload            # :8000
cd web && API_URL=http://localhost:8000 NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Tests and gates

```bash
make lint     # ruff, mypy --strict, eslint, tsc
make test     # pytest (needs Postgres + Redis) and vitest
make gates    # C1 robots, W7 ads, W3 JSON-LD, W4–W6 SSR/sitemaps/canonicals
```

| Gate | Where |
|---|---|
| C1 robots / C2 rate limit / C3 403 flip / C4 304 | `scripts/validate_robots.py`, `crawler/tests/test_{robots,ratelimit,fetcher}.py` |
| C5 extractor fixtures / C6 LLM budget | `crawler/tests/test_extract_fixtures.py`, `test_llm.py` |
| R1 precision/recall / R2 packages / R3 audit | `resolver/tests/` |
| P1 FX / P2 golden ranker / P3 freshness / P4 alerts | `price/tests/` |
| A2 zero-result / A3 rate limit | `api/tests/test_api.py` |
| W3 JSON-LD / W4 SSR / W5 sitemaps / W6 canonicals | `web/scripts/validate-schema.ts`, `web/scripts/site-check.mjs` |
| W7 ads policy | `scripts/check_ads_policy.py`, `tests/python/test_ads_policy.py` |
| E2 search → click-out / E3 mobile 375×667 | `web/e2e/journeys.spec.ts` (`npm run e2e`) |
| Benchmarks (not gates): A1 load, W1/W2 Lighthouse, E1 full Docker stack | `scripts/bench_search.py`, `web/scripts/lighthouse-ci.js`, `make demo` |

## Going live — what a human must do

1. For each source in `crawler/sources.yaml`: verify the domain, read its Terms of Service,
   then set `legal_review: {status: approved, reviewed_by, reviewed_at, notes}`. Run
   `python scripts/validate_robots.py` (it fetches robots.txt live).
2. Apply for API keys (Mouser, DigiKey, YouTube, GitHub) and accept their terms.
   Reddit needs a commercial agreement. LCSC's client is not written yet: their API docs
   come with the key.
3. Review `price/duty.py` rates against the current NBR tariff.
4. Set real secrets (`SECRET_KEY`, `ADMIN_TOKEN_SHA256`, `TYPESENSE_API_KEY`, SMTP) and AdSense IDs.
5. Replace the synthetic extractor fixtures and the R1 set with saved real pages/listings
   once sources are approved, and re-measure.

## Licence

MIT — see [LICENSE](LICENSE). Data shown on the site belongs to its sources.
