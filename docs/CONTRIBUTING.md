# Contributing

* Python 3.12+, `ruff check`, `ruff format`, `mypy --strict` must pass. TypeScript `strict`, ESLint (no `any`, no `as` assertions in app code).
* SQL lives in repository functions (`api/app/repository.py`, `price/repository.py`, `resolver/pg_index.py`), never in routers.
* Every outbound HTTP call goes through `common.http.ApiClient` (timeouts, retries, circuit breaker) or the crawler `Fetcher`.
* **Legal rules are code.** If you change `docs/LEGAL.md`, change the enforcing module and its test in the same PR.
* Extractor change → `python scripts/regen_extract_fixtures.py` and review every line of the `.expected.json` diff.
* Ranking change → `python scripts/regen_ranker_golden.py`, then check the printed table by hand.
* API schema change → `python scripts/export_web_fixtures.py` so the web contract tests see it.
* No skipped tests on `main`.
