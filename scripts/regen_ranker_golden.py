#!/usr/bin/env python3
"""Regenerate price/tests/golden_ranker.json (P2). Review the printed table before committing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from price.ranker import RankRequest, SortMode, rank_offers  # noqa: E402
from price.tests.golden_scenarios import FX, GEOS, NOW, QUOTES, SCENARIOS  # noqa: E402

OUT = ROOT / "price" / "tests" / "golden_ranker.json"


def main() -> None:
    cases = []
    for scen, (qty, offers) in SCENARIOS.items():
        for geo_name, geo in GEOS.items():
            row: dict[str, object] = {"scenario": scen, "geo": geo_name}
            for mode in SortMode:
                ranked = rank_offers(offers, RankRequest(geo=geo, quantity=qty, mode=mode), FX, NOW, QUOTES)
                row[mode.value] = [r.offer.source_name for r in ranked[:3]]
                if mode is SortMode.BEST:
                    print(
                        f"{scen:15} {geo_name:11} best={row['best']}  "
                        f"landed$={[round(r.unit_landed_usd_micros / 1e6, 3) for r in ranked[:3]]} "
                        f"eta={[r.eta_days for r in ranked[:3]]}"
                    )
            cases.append(row)
    OUT.write_text(json.dumps(cases, indent=1) + "\n")
    print(f"{len(cases)} cases → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
