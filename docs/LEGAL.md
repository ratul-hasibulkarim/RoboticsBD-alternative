# VoltFind — Legal & Ethical Guardrails

These rules are **enforced in code**. Each rule names the module that enforces
it and the test that proves it. If you change a rule, change the code and the
test in the same pull request.

> This document is engineering policy, not legal advice. Before a source is
> set to `approved`, a human must read that site's Terms of Service and record
> the decision in `crawler/sources.yaml` (`legal_review` block).

## 1. What VoltFind is

VoltFind is a read-only index of public product information (title, part
number, price, stock, spec values, image URL, datasheet URL). It does not
sell, ship or hold stock. Every fact shown links to where it came from.

## 2. Rules the crawler must obey

| # | Rule | Enforced in | Test |
|---|---|---|---|
| 1 | Honour `robots.txt` on every host. Cached in Redis for 24 h, re-fetched after. **Fail closed**: if robots.txt cannot be fetched (network error, 5xx), the host is treated as fully disallowed. A 4xx (other than 429) means "no robots file" → allowed, per RFC 9309 §2.3.1.3. | `crawler/fetcher/robots.py` | `crawler/tests/test_robots.py`, `scripts/validate_robots.py` (C1) |
| 2 | Honour `Crawl-delay` and per-host rate limits. Default 1 request / 2 s per host (0.5 rps). Effective rate = `min(source.rate_limit_rps, 1/crawl_delay)`. | `crawler/fetcher/ratelimit.py` | `test_ratelimit.py` (C2) |
| 3 | Identify honestly: `User-Agent: VoltFindBot/1.0 (+https://voltfind.com/bot)`. The UA is a constant; there is no code path to change it per request. | `crawler/fetcher/client.py` | `test_fetcher.py::test_user_agent_is_constant` |
| 4 | Respect `Retry-After` on 429/503. Exponential backoff with full jitter, capped at 1 h, max 3 retries. | `crawler/fetcher/worker.py` | `test_fetcher.py::test_retry_after_*` |
| 5 | Never fetch behind a login. No cookies are stored or sent (`httpx` client is created with a no-op cookie jar). Pages detected as login walls, paywalls or CAPTCHA challenges are discarded and the source flips to `review_required`. | `crawler/fetcher/client.py`, `crawler/fetcher/walls.py` | `test_fetcher.py::test_login_wall_*` |
| 6 | Never retain personal data. Pages with e-mail addresses / phone numbers outside a product-offer context, or user-profile markup, are dropped before extraction output is stored. | `crawler/extractors/pii.py` | `test_pii.py` |
| 7 | Store only what is needed: price, title, MPN, specs, image **URL**, datasheet **URL**, ≤ 300-char snippet. Raw HTML is held in object storage for at most 30 days for re-extraction, then deleted. Datasheet PDFs are never downloaded. | `crawler/fetcher/worker.py` (5 MB cap, PDF/video/archive skip), `crawler/tasks.py::purge_raw_pages` | `test_fetcher.py::test_skips_pdf` |
| 8 | Attribution is mandatory: every price, image and datasheet in the UI shows the source name and links to the source URL. | `web/components/SourceBadge.tsx`, `OfferRow.tsx` | `web/tests/attribution.test.tsx` |
| 9 | On HTTP 403 or 451 from a source: stop immediately and set `crawl_status = review_required`. | `crawler/fetcher/worker.py` | `test_fetcher.py::test_403_flips_source` (C3) |
| 10 | Nothing is queued for a source unless `legal_review_status == "approved"` and `active == true`. | `crawler/registry.py`, `crawler/tasks.py` | `test_registry.py` |

## 3. Platform-specific rules

| Platform | Method | Status | Reason |
|---|---|---|---|
| Mouser, Digi-Key, LCSC, element14/Farnell, Arrow | Official product-search APIs with our own key. Polite crawl is **not** used as a fallback unless the ToS permits it. | `pending` until keys are issued and the API terms (display + caching limits) are accepted by the owner. | APIs are faster, richer and permitted. Each API's terms cap cache lifetime — honoured via `sources.yaml: cache_ttl_hours`. |
| Manufacturer sites (TI, ST, Microchip, Espressif, Raspberry Pi, Arduino) | `sitemap.xml` walk, robots-allowed product pages, datasheet **link** only. | `pending` | |
| BD shops (RoboticsBD, TechShopBD, etc.) | Polite crawl of public product pages; or the shop submits a feed. | `pending` until the owner reads each shop's ToS. | |
| YouTube | YouTube Data API v3: title, description, thumbnail URL, channel, link. No transcripts; data refreshed or deleted within 30 days per YouTube API Services policy. | `pending` (needs API key) | |
| GitHub | REST API search (authenticated, within rate limits). README excerpt ≤ 600 chars + link; code only when the repo license allows redistribution. | `pending` (needs token) | |
| Reddit | Official Data API (OAuth) only. | `pending` until a **commercial** Data API agreement exists. | Free tier is non-commercial. |
| Facebook / Instagram | Not crawled, not called. Shops may submit their own listings. | `blocked` | Meta's ToS forbid automated collection without permission; Page Public Content Access requires app review we do not have. |
| Google / Bing / Yahoo search results | Not used. | `blocked` | SERP scraping violates their ToS; Bing APIs are retired; Google Custom Search JSON API is closed to new customers. |

## 4. Takedown & opt-out

Any site owner can ask to be removed at `/legal/opt-out`. The request is stored
in `takedown_requests`. On review the source is set to `blocked`, its listings
are deactivated, and its raw pages are purged within 24 h. The `/bot` page
explains what the bot does and how to block it (`User-agent: VoltFindBot`).

## 5. Users

We store an e-mail address only when a user creates a price alert. Search
analytics store a salted, daily-rotated hash of the session, never IP
addresses. Users can delete their account and all alerts from `/alerts`.
