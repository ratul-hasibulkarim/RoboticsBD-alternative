# Runbook

## A source flipped to `review_required`
Cause: HTTP 403/451, or a login/CAPTCHA/paywall page was detected (reason in `sources.crawl_status_reason`).
1. Open the site manually. Was the block deliberate (new robots rule, bot protection)?
2. If the site doesn't want us: set `legal_review.status: blocked` in `sources.yaml` and run `make sync-sources`.
3. If it was transient: `POST /v1/admin/sources/{name}/crawl-status {"status":"ok","reason":"…"}`.
   **Never** add workarounds (other UAs, proxies, cookies).

## Opt-out / takedown request
1. Admin → review queue (kind `takedown`) → verify the requester controls the domain (mail from the domain or a DNS TXT record).
2. `POST /v1/admin/takedowns/{id} {"accept": true}` blocks the source and hides its listings at once.
3. Set `legal_review.status: blocked` in `sources.yaml` in the same day (the sync would otherwise reactivate it).
4. Raw pages are purged by `purge_raw` within 24 h.

## LLM budget hit
The `fetch_url` task retries in 6 h; rule-based extraction keeps running. Check `llm_extraction_log` for unusual volume.

## Typesense down
Search falls back to Postgres automatically (response field `backend: "postgres"`). Re-index after recovery:
`python -c "import asyncio; from search.indexer import *; …"`, or trigger `index_component` per part.

## FX refresh failing
Pricing keeps using the latest stored day. If more than 3 days stale, check `open.er-api.com` reachability.

## Retiring a part
`PATCH /v1/admin/components/{id} {"status":"retired"}` → the page answers 410 within 10 minutes (middleware cache).

## Wrong merge
`POST /v1/admin/components/{id}/split` with the listing IDs that belong elsewhere. Both components are re-indexed and the split is audited.
