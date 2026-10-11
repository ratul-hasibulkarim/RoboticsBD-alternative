#!/usr/bin/env python3
"""Regenerate crawler/tests/fixtures/extract/*.expected.json from the current extractors.

Only run this after a deliberate extractor change, and review the git diff of the
.expected.json files line by line before committing — they are the C5 contract.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.extractors.pipeline import extract  # noqa: E402
from crawler.tests.conftest import make_source  # noqa: E402

FIXTURES = ROOT / "crawler" / "tests" / "fixtures" / "extract"


async def main() -> int:
    for case in yaml.safe_load((FIXTURES / "cases.yaml").read_text()):
        src = make_source(extractor=case["extractor"], currency=case["currency"], domain="shop.test")
        res = await extract((FIXTURES / case["file"]).read_bytes(), case["url"], src)
        out = {
            "outcome": str(res.outcome),
            "listing": res.listing.model_dump(mode="json") if res.listing else None,
        }
        target = FIXTURES / (Path(case["file"]).stem + ".expected.json")
        target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)} ({res.outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
