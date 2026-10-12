PY ?= python
NPM ?= npm
.DEFAULT_GOAL := help

help:  ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

install:  ## install Python + web dependencies
	$(PY) -m pip install -e ".[dev]"
	cd web && $(NPM) ci

migrate:  ## apply database migrations
	$(PY) -m alembic -c api/alembic.ini upgrade head

sync-sources:  ## load crawler/sources.yaml into the sources table
	$(PY) scripts/sync_sources.py

lint:  ## ruff + mypy + eslint + tsc
	ruff check .
	mypy common crawler resolver price search api scripts
	cd web && $(NPM) run -s lint && $(NPM) run -s typecheck

test:  ## all Python + web unit/integration suites
	$(PY) -m pytest -q
	cd web && $(NPM) test

gates:  ## CI gates: robots (C1), ads policy (W7), JSON-LD (W3), site check (W4–W6)
	$(PY) scripts/validate_robots.py
	$(PY) scripts/check_ads_policy.py
	cd web && $(NPM) run -s validate:schema && $(NPM) run -s check:site && $(NPM) run -s e2e

web-fixtures:  ## re-export API responses used by web contract tests
	$(PY) scripts/export_web_fixtures.py

demo:  ## E1: boot the full stack and seed 500 demo components
	docker compose up -d --build
	docker compose run --rm api python scripts/seed_demo_data.py --components 500
	@echo "site: http://localhost:3000  api: http://localhost:8000/docs  mail: http://localhost:8025"

down:  ## stop the stack
	docker compose down

.PHONY: help install migrate sync-sources lint test gates web-fixtures demo down
