#!/usr/bin/env python3
"""Load crawler/sources.yaml into the `sources` table (legal status in YAML always wins)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.db import session_scope
from crawler.registry import load_registry, sync_sources_to_db


async def main() -> None:
    async with session_scope() as s:
        n = await sync_sources_to_db(s, load_registry())
    print(f"synced {n} sources")


if __name__ == "__main__":
    asyncio.run(main())
