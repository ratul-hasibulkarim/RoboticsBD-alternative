#!/usr/bin/env python3
"""CI gate C1: every approved + active crawl source must be allowed by its robots.txt.

Checks, for each source with legal_review.status == approved and active == true:
  * sources.yaml validates (schema, approvals carry reviewer + date)
  * robots.txt is reachable (fail closed: unreachable → FAIL)
  * base_url and every seed URL are allowed for VoltFindBot
  * the declared rate_limit_rps does not exceed robots Crawl-delay / Request-rate

Exit code 0 = pass, 1 = at least one failure. With --write-db, records
robots_checked_at / robots_hash in the sources table.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.settings import get_settings  # noqa: E402
from crawler.fetcher.client import build_crawler_client  # noqa: E402
from crawler.fetcher.robots import fetch_robots, origin_of  # noqa: E402
from crawler.registry import SourceConfig, load_registry  # noqa: E402


async def check_source(src: SourceConfig) -> list[str]:
    errors: list[str] = []
    urls = [str(src.base_url)] + [str(s.url) for s in src.seeds if s.url is not None]
    async with build_crawler_client() as client:
        origins = sorted({origin_of(u) for u in urls})
        for origin in origins:
            rules = await fetch_robots(client, origin)
            if rules.state == "unreachable":
                errors.append(f"{src.name}: robots.txt unreachable at {origin} (fail closed)")
                continue
            for u in urls:
                if origin_of(u) == origin and not rules.can_fetch(u):
                    errors.append(f"{src.name}: robots.txt disallows {u}")
            delay = rules.crawl_delay()
            if delay and src.rate_limit_rps > 1.0 / delay:
                errors.append(
                    f"{src.name}: rate_limit_rps={src.rate_limit_rps} exceeds Crawl-delay {delay}s "
                    "(fetcher would clamp it, but the registry must not declare more)"
                )
    return errors


async def write_db(results: dict[str, str]) -> None:
    from sqlalchemy import update

    from common.db import session_scope
    from common.models import Source
    from common.timeutil import utcnow

    async with session_scope() as s:
        for name, digest in results.items():
            await s.execute(
                update(Source)
                .where(Source.name == name)
                .values(robots_checked_at=utcnow(), robots_hash=digest)
            )


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", type=Path, default=get_settings().sources_file)
    ap.add_argument("--write-db", action="store_true")
    args = ap.parse_args(argv)

    try:
        registry = load_registry(args.sources)
    except Exception as exc:  # validation errors must fail CI with a readable message
        print(f"FAIL sources.yaml invalid: {exc}")
        return 1

    targets = [s for s in registry.approved() if s.type == "crawl"]
    print(f"{len(registry.sources)} sources, {len(targets)} approved crawl sources to verify")
    all_errors: list[str] = []
    digests: dict[str, str] = {}
    for src in targets:
        errs = await check_source(src)
        all_errors.extend(errs)
        print(("FAIL " if errs else "ok   ") + src.name)
        if not errs:
            async with build_crawler_client() as c:
                digests[src.name] = (await fetch_robots(c, origin_of(str(src.base_url)))).sha256

    for e in all_errors:
        print("  - " + e)
    if args.write_db and digests:
        await write_db(digests)
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
