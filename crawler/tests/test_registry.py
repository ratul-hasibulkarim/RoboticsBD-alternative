"""The legal gate: only approved + active sources are ever returned for crawling."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
import yaml
from pydantic import ValidationError

from crawler.registry import NotApprovedError, approved_sources, load_registry
from crawler.tests.conftest import make_source
from scripts.validate_robots import check_source

REPO_SOURCES = Path(__file__).resolve().parents[1] / "sources.yaml"


def test_repo_sources_yaml_is_valid() -> None:
    reg = load_registry(REPO_SOURCES)
    assert len(reg.sources) >= 10
    for blocked in ("facebook", "instagram", "search-engines"):
        assert reg.get(blocked).legal_review.status == "blocked"
        assert not reg.get(blocked).is_approved
    assert reg.get("reddit").legal_review.status != "approved"


def test_only_approved_and_active_are_returned(tmp_path: Path) -> None:
    raw = yaml.safe_load(REPO_SOURCES.read_text())
    raw["sources"][0]["legal_review"].update(status="approved", reviewed_by="qa", reviewed_at="2026-10-01")
    raw["sources"][1]["legal_review"].update(status="approved", reviewed_by="qa", reviewed_at="2026-10-01")
    raw["sources"][1]["active"] = False
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump(raw))
    names = [s.name for s in approved_sources(p)]
    assert names == [raw["sources"][0]["name"]]


def test_approval_without_reviewer_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_source(legal_review={"status": "approved"})


def test_require_approved_raises() -> None:
    with pytest.raises(NotApprovedError):
        make_source(legal_review={"status": "blocked"}).require_approved()
    make_source().require_approved()


def test_crawl_source_requires_robots_url() -> None:
    with pytest.raises(ValidationError):
        make_source(robots_url=None)


def test_affiliate_template_must_contain_url() -> None:
    with pytest.raises(ValidationError):
        make_source(affiliate_template="https://aff.test/?to=")
    assert make_source(affiliate_template="https://aff.test/?to={url}").affiliate_template


def test_duplicate_names_rejected(tmp_path: Path) -> None:
    raw = yaml.safe_load(REPO_SOURCES.read_text())
    raw["sources"].append(raw["sources"][0])
    p = tmp_path / "dup.yaml"
    p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValidationError):
        load_registry(p)


def test_for_host_matches_subdomains() -> None:
    reg = load_registry(REPO_SOURCES)
    src = reg.for_host("www.roboticsbd.com")
    assert src is not None and src.name == "roboticsbd"
    assert reg.for_host("example.org") is None


@respx.mock
async def test_validate_robots_flags_disallowed_seed() -> None:
    respx.get("https://shop.test/robots.txt").respond(200, text="User-agent: VoltFindBot\nDisallow: /\n")
    errs = await check_source(make_source())
    assert errs and "disallows" in errs[0]


@respx.mock
async def test_validate_robots_fails_closed() -> None:
    respx.get("https://shop.test/robots.txt").respond(500)
    errs = await check_source(make_source())
    assert errs and "unreachable" in errs[0]


@respx.mock
async def test_validate_robots_passes_when_allowed() -> None:
    respx.get("https://shop.test/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
    assert await check_source(make_source(rate_limit_rps=0.5)) == []


@respx.mock
async def test_validate_robots_flags_rate_above_crawl_delay() -> None:
    respx.get("https://shop.test/robots.txt").respond(200, text="User-agent: *\nCrawl-delay: 10\n")
    errs = await check_source(make_source(rate_limit_rps=0.5))
    assert errs and "Crawl-delay" in errs[0]
