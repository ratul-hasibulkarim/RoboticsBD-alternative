#!/usr/bin/env python3
"""A1 benchmark (not a CI gate): search latency percentiles under concurrent load.

    python scripts/bench_search.py --url http://localhost:8000 --rps 1000 --seconds 30
Targets: p50 < 30 ms, p95 < 80 ms, p99 < 150 ms.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time

import httpx

QUERIES = [
    "esp32",
    "ESP32-WROOM-32E",
    "74hc595",
    "lm2596",
    "buck converter",
    "ultrasonic sensor",
    "ne555",
    "op amp",
    "stm32",
    "dht22",
    "10k resistor 0805",
    "mosfet logic level",
    "usb to ttl",
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--rps", type=int, default=200)
    ap.add_argument("--seconds", type=int, default=20)
    a = ap.parse_args()
    lat: list[float] = []
    errors = 0
    async with httpx.AsyncClient(base_url=a.url, timeout=5, limits=httpx.Limits(max_connections=500)) as c:

        async def one(i: int) -> None:
            nonlocal errors
            t0 = time.perf_counter()
            r = await c.get(
                "/v1/search",
                params={"q": random.choice(QUERIES)},
                headers={"CF-Connecting-IP": f"10.0.{i % 250}.{i % 7}"},
            )
            if r.status_code != 200:
                errors += 1
            lat.append((time.perf_counter() - t0) * 1000)

        tasks = []
        start = time.perf_counter()
        for i in range(a.rps * a.seconds):
            tasks.append(asyncio.create_task(one(i)))
            await asyncio.sleep(max(0.0, start + (i + 1) / a.rps - time.perf_counter()))
        await asyncio.gather(*tasks)
    q = statistics.quantiles(lat, n=100)
    print(f"requests={len(lat)} errors={errors} p50={q[49]:.1f}ms p95={q[94]:.1f}ms p99={q[98]:.1f}ms")


if __name__ == "__main__":
    asyncio.run(main())
