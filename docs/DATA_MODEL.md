# Data model

Source of truth: `api/alembic/versions/0001_init.py`. ORM mirror: `common/models.py`.

| Table | Purpose | Notes |
|---|---|---|
| `sources` | Every data source + its legal status | `legal_review_status` comes from `sources.yaml` only; `crawl_status` is runtime state (`ok/review_required/failing/disabled`) set by the fetcher or admins |
| `crawl_pages` | One row per fetched URL | ETag / Last-Modified for conditional GET; `raw_ref` points at raw HTML that is deleted after 30 days |
| `listings` | A product page / API record at one source | `mpn_trusted` = MPN came from a structured field, not a title guess; `component_id` set by the resolver |
| `components` | The canonical part | unique `(mpn_norm, manufacturer_norm)` among active parts; `status` active/merged/retired; `embedding vector(384)` with HNSW index |
| `price_snapshots` | Price history (hypertable when Timescale is present) | written on change + at least daily; 90-day retention |
| `price_current` | Latest price per listing | `price_usd_minor`, `landed_usd_minor` for sorting/indexing |
| `price_daily` | Daily rollup | min/max/close per listing; 5-year retention; feeds sparklines |
| `fx_rates` | Units per USD by day | refreshed every 6 h; the latest row on or before a date is used |
| `images`, `component_images` | Image URLs + attribution | `s3_key` only allowed for redistributable licences (DB CHECK) |
| `datasheets` | Links to publisher-hosted datasheets | one primary per component (partial unique index) |
| `use_cases` | Tutorials: summary ≤ 600 chars + link | `code_snippet` only with a `code_license` (DB CHECK) |
| `ship_estimates` | Source → country shipping cost + ETA | used by the ranker when present, else defaults |
| `queries`, `component_views_daily` | Anonymised analytics | session hash rotates daily; views drive `crawl_priority` |
| `users`, `price_alerts` | Alerts with armed/disarmed state | fire once per crossing; 2 % re-arm hysteresis |
| `merge_audit` | Every attach / create / merge / split | written by resolver and admin actions |
| `review_queue` | Human review: low-confidence matches, LLM output, takedowns, submissions | one open item per (kind, ref_id) |
| `llm_extraction_log` | Every LLM call: input hash, output, confidence, cost | |
| `takedown_requests`, `data_reports`, `guides` | Opt-outs, user error reports, reviewed long-form guides | guides cannot be `published` without `reviewed_by` (DB CHECK) |

View `crawl_priority`: per active listing on an approved, healthy crawl source. Gives the
recrawl interval (6 h for the top 5 % by 7-day views, 24 h for the top half, 7 days otherwise)
and `next_due`, with exponential backoff on consecutive failures. Listings are deactivated
after 5 failures.
