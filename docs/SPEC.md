# VoltFind — Revised Build Specification (v1.1)

This file is the binding spec. It supersedes the original v1.0 prompt. Every
change from v1.0 is listed in §0 with the reason, so reviewers can audit why
the code differs from the original text.

---

## 0. Changes from v1.0

| # | v1.0 said | v1.1 does | Why |
|---|---|---|---|
| 1 | `all-MiniLM-L6-v2` (768-d) | **384-d** everywhere (`vector(384)`, Typesense `num_dim: 384`) | That model outputs 384 dimensions; 768 would reject every vector. |
| 2 | AdMob | **Google AdSense** (web) | AdMob serves ads only in native mobile apps. |
| 3 | Google / Yahoo / Bing search APIs for discovery | **Removed.** Discovery = sitemaps, distributor catalogs, manual submissions, outbound links on approved sources. | Bing Search APIs retired 2025-08-11; Yahoo has no public API; Google Custom Search JSON API closed to new customers and ends 2027-01-01. |
| 4 | Reddit "free tier" | Reddit source is `pending` until a commercial Data API agreement exists. Client code ships but is gated. | Free tier is non-commercial only; an ad-funded site is commercial. |
| 5 | Facebook / Instagram Graph API for public Pages | `blocked`. BD shops can **submit listings / feeds** instead (`type: manual` / `feed`). | Page Public Content Access needs Meta app review that aggregators rarely pass; there is no Marketplace partner API available to us. |
| 6 | YouTube video + transcript | Title, description, thumbnail URL, channel, link. **No transcripts.** | The official API only lets owners download captions. |
| 7 | `reppy` | **`protego`** | reppy is unmaintained and does not build on 3.12+. protego supports `Crawl-delay`, wildcards. |
| 8 | FAQPage / HowTo for rich results | Emitted as valid markup but **not counted on** for rich results. Product + AggregateOffer + BreadcrumbList are the priority. | Google restricted FAQ rich results to gov/health sites and dropped HowTo rich results (2023). |
| 9 | Validate via Google Rich Results Test in CI | Offline validation: typed builders + Zod schemas + required-property checks (`web/scripts/validate-schema.ts`). | Rich Results Test has no API. |
| 10 | "BD law prohibits scraping" | Removed. LEGAL.md cites only verifiable sources (each platform's ToS). | Unverified legal claims do not belong in a legal doc. |
| 11 | Images stored in S3/MinIO; datasheet first-page previews; full `body_md` tutorials | **Images hotlinked with attribution** (S3 only for `license in {manufacturer, cc-by, cc-by-sa, cc0, submitted}`); **no datasheet previews**; use-cases store a **≤ 600-char summary + link**, code only when its license permits redistribution. | Resolves contradiction with the "never mirror" rule and copyright exposure. |
| 12 | Ranker adds local-currency price + shipping + USD duty | All costs converted to one currency before arithmetic: integer **micro-USD** internally (cents lose ~৳1 per BDT round trip), cents for storage/API. | Mixed-currency sums are wrong; cents are too coarse for cheap parts. |
| 13 | Single price per listing | `price_breaks JSONB` `[{qty, price_minor}]`; landed cost computed at the user's requested quantity. | Distributors price by quantity tier. |
| 14 | Confidence thresholds unclear (0.80/0.85/0.95) | **Attach listing → component** at ≥ 0.85; 0.80–0.85 → manual review; **merge two components** at ≥ 0.95 only. | Two different operations need two thresholds. |
| 15 | Fetcher sets `status='review_required'` (no such column) | New `sources.crawl_status` (`ok|review_required|failing|disabled`) independent of `legal_review_status`. | A crawl error must never overwrite a legal decision. |
| 16 | `rel="sponsored"` on every outbound link | `sponsored` only on affiliate/paid links; others `nofollow noopener`. | Correct use of link attributes. |
| 17 | `hreflang` en/bn | Emitted only when a `bn` translation of that page exists. | hreflang to a missing page is an error. |
| 18 | Redis Streams **and** Celery | **Celery on Redis** only (named queues per stage). | Celery does not use Streams; two queue systems is waste. |
| 19 | Missing tables/columns | Added: `merge_audit`, `review_queue`, `gtin`, `etag`/`last_modified`, `price_breaks`, `component_views_daily`, `price_daily`, `fx_rates`, `sources.trust_score`, `sources.affiliate_template`, `sources.crawl_status`, `sources.warehouse_*`, `listings.mpn_trusted`, `price_alerts.armed`, `takedown_requests`, `data_reports`, `guides`, `llm_extraction_log`. Shop submissions use `review_queue` (kind `submission`). | Referenced by v1.0 but never defined. |
| 20 | `components.primary_image` FK before `images` exists; no extensions | Migration orders tables correctly and enables `pgcrypto`, `citext`, `vector` (+ `timescaledb` when available). | Migration would fail. |
| 21 | ivfflat index on empty table | **HNSW** index. | ivfflat needs data present at build time to cluster. |
| 22 | Nominatim self-hosted | Static BD + world-capital city table (`price/geo_data.py`) + IP→country header from Cloudflare (`CF-IPCountry`). | Planet import is hundreds of GB for a city lookup. |
| 23 | Duty from HS tariffs | Per-category flat **estimate** table for BD (labelled "estimate" in UI), pluggable. | Full HS tables are a project of their own. |
| 24 | 100k pages pre-built | Top **1 000** pre-built, rest on-demand ISR. | Build time. |
| 25 | Pro tier billing undefined | Out of scope for v1.1 (explicitly). Alerts limited by a constant. | Stripe does not onboard BD merchants; needs SSLCommerz/bKash decision by owner. |
| 26 | No opt-out | `takedown_requests` + `/legal/opt-out` form; an opt-out sets `legal_review_status='blocked'` on review. | Shops will ask on day one. |
| 27 | User auth undefined | Email magic link (HMAC-signed, 30 min) → 30-day session token for alerts. Admin API: bearer tokens whose SHA-256 digests are listed in `ADMIN_TOKEN_SHA256`. | Minimal, no third-party IdP, no passwords stored. |
| 28 | Several acceptance tests not runnable in CI | CI gates: C1–C5, R1–R3 (fixture set is synthetic-but-realistic and labelled as such), P1–P4, A2–A3, W3–W7, E3. **Benchmarks (not merge gates):** A1 (load), W1/W2 (Lighthouse, needs a deployed URL), C6 (time-travel test runs in CI using a fake clock), E1/E2 (need Docker). | CI container cannot do 1000 rps or real prices without API keys. |
| 30 | Cascade step 4 (MPN fuzzy ≤ 1 + manufacturer exact → 0.85 attach) | Step 4 produces a **review suggestion**, never an automatic attach, and only for MPNs guessed from titles. | One character usually *is* a different part (CH340C/CH340G, BMP280/BME280, ATmega328/328P). Observed on the R1 set: it caused every precision error. |
| 31 | — | **Trusted-first creation**: a listing whose MPN was only guessed from its title and has no match is **deferred** and retried 24 h later before it may create a component. Components store the MPN without packaging suffixes. | A title guess can pick the wrong token ("ESP8266" in "ESP 12F ESP8266 module"); distributor/API listings get the first chance to create the canonical part. |
| 29 | Repo root `voltfind/` | Repo root **is** the project root. | Repo already exists. |

---

## 1. Product

Read-only intelligence layer over electronics listings. Never sells, ships, or
holds stock. Links out to the source. Target: query → right part → best price
→ click-out in < 30 s.

## 2. Legal

See [LEGAL.md](LEGAL.md). Enforced in code by:

- `crawler/registry.py` — refuses to load a source unless `legal_review_status == "approved"` and `active`.
- `crawler/fetcher/robots.py` — protego, 24 h Redis cache, fail-closed.
- `crawler/fetcher/ratelimit.py` — Redis token bucket, `min(declared, crawl-delay)`.
- `crawler/fetcher/worker.py` — honest UA, no cookies, Retry-After, 403/451 → `crawl_status=review_required`.
- `crawler/extractors/pii.py` — drops pages that look like personal data.
- `scripts/validate_robots.py` — CI gate.

## 3. Architecture

```
Next.js 15 (SSR/ISR)  ──HTTPS──▶  FastAPI gateway  ──▶  Postgres16 + pgvector (+Timescale)
                                        │                 Typesense
                                        │                 Redis (cache, RL, Celery broker)
Celery Beat ─▶ queues: crawl.fetch ─▶ crawl.extract ─▶ crawl.resolve ─▶ price.snapshot ─▶ search.index
```

Stack is as v1.0 §3.1 except the changes in §0.

## 4. Data model

See [DATA_MODEL.md](DATA_MODEL.md) and `api/alembic/versions/0001_init.py`.

## 5–8. Crawler, resolver, price, search

As v1.0 with §0 changes. Module map:

| Concern | Module |
|---|---|
| Source registry / legal gate | `crawler/registry.py`, `crawler/sources.yaml` |
| Seeds | `crawler/seeds/` (sitemap walker, category walker, distributor API pagers) |
| Fetcher | `crawler/fetcher/{robots,ratelimit,client,worker}.py` |
| Extraction | `crawler/extractors/{jsonld,microdata,opengraph,pipeline,pii,llm}.py`, `per_source/*.py` |
| Normalisation | `crawler/normalizer/{mpn,units,currency,country}.py` |
| Resolution | `resolver/{matcher,embedder,merge_audit,service}.py` |
| Price | `price/{fx,duty,geo,ranker,snapshotter,alerts}.py` |
| Search | `search/{schema.json,synonyms.json,indexer.py,query_understanding.py}` |
| API | `api/app/` |
| Web | `web/` |

## 9–11. Frontend, SEO, Ads

As v1.0 with §0 changes (AdSense, hreflang, rich results, rel attributes).
Ad policy: `ads/placement_policy.yaml`, enforced by `web/components/ads/AdSlot.tsx`
(and re-exported from `ads/adapter.tsx`) and `scripts/check_ads_policy.py`.

## 13. Acceptance tests

See §0 row 28 for what is a CI gate vs a benchmark.
