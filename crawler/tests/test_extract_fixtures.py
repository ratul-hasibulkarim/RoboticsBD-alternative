"""C5: every fixture HTML extracts exactly its expected JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from crawler.extractors.pipeline import extract
from crawler.tests.conftest import make_source

FIXTURES = Path(__file__).parent / "fixtures" / "extract"
CASES: list[dict[str, Any]] = yaml.safe_load((FIXTURES / "cases.yaml").read_text())


def test_every_fixture_has_expected_json() -> None:
    html_files = {p.name for p in FIXTURES.glob("*.html")}
    listed = {c["file"] for c in CASES}
    assert html_files == listed, f"unlisted fixtures: {html_files - listed}"
    for c in CASES:
        assert (FIXTURES / (Path(c["file"]).stem + ".expected.json")).exists(), c["file"]


@pytest.mark.parametrize("case", CASES, ids=[c["file"] for c in CASES])
async def test_fixture_extracts_expected(case: dict[str, Any]) -> None:
    src = make_source(extractor=case["extractor"], currency=case["currency"], domain="shop.test")
    res = await extract((FIXTURES / case["file"]).read_bytes(), case["url"], src)
    expected = json.loads((FIXTURES / (Path(case["file"]).stem + ".expected.json")).read_text())
    assert str(res.outcome) == case["outcome"] == expected["outcome"]
    got = res.listing.model_dump(mode="json") if res.listing else None
    assert got == expected["listing"]
