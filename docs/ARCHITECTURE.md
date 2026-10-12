# Architecture

```
Browser ──▶ Cloudflare ──▶ Next.js 15 (ISR, :3000) ──▶ FastAPI (:8000) ──▶ Postgres 16 + pgvector (+Timescale)
                                   │  /go/:id rewrite ─────▶│                    Typesense 27 (search)
                                   │◀── /api/revalidate ────┤                    Redis 7 (cache, rate limits, Celery broker)
                                                            │                    MinIO/S3 (raw HTML, 30-day TTL)
Celery beat ─▶ crawl.seed ─▶ crawl.fetch (fetch+extract+price) ─▶ crawl.resolve ─▶ search.index ─▶ ISR revalidate
           └─▶ maintenance: fx_refresh (6 h), run_alerts (15 min), schedule_due (10 min), discover (15 min),
                            resolve_deferred (1 h), retention (daily), purge_raw (daily)
```

## Request path for a component page
1. Next.js serves `/component/[slug]` from ISR (pre-built for the top 1 000 parts, `revalidate: 3600`).
   The page renders for the default market (Dhaka, BDT). All prices, specs and JSON-LD are in the HTML.
2. In the browser, `OffersPanel` reads the visitor's saved location (`vf_geo` cookie). If it differs,
   offers are re-ranked via `GET /v1/components/{slug}/offers`.
3. "View at <shop>" goes to `/go/{listing_id}`. The API logs an anonymous click and 302s to the
   seller, applying an affiliate template only where the source has one (`rel="sponsored"`).

## Ingestion path for one product URL
`fetch_url` task → `Fetcher.fetch` (legal gate → crawl_status → robots → rate limit → conditional GET)
→ `extract` (rules → LLM if needed) → `upsert_listing` + `price.snapshotter.record`
→ `resolve` task (`Resolver`: attach / create / review / defer) → `index_component` → Typesense + ISR revalidate.

## Key decisions
* **One queue system** (Celery on Redis). Each stage is its own queue so they scale independently.
* **Money**: stored in minor units per currency; ranked in integer micro-USD; shown in BDT/USD/EUR.
* **Embeddings**: 384-d everywhere. The hashing embedder (no model download) is the default.
  Set `EMBEDDING_BACKEND=sentence-transformers` and install `.[ml]` for MiniLM.
* **Search resilience**: if Typesense is down, the API falls back to Postgres search (slower, same response).
* **Geo**: Cloudflare `CF-IPCountry` / `cf-ipcity` headers plus a static city table. No geocoder service.
