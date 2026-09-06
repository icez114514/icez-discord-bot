"""Opt-in isolated-schema latency benchmark; never benchmarks production accounts."""
import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path
from uuid import uuid4
from psycopg import sql
from database import Account, CrystalStore, read_database_url
from casino_store import CasinoStore
from runtime import configure_event_loop

async def benchmark(args):
    schema = "casino_test_" + uuid4().hex
    crystals = CrystalStore(read_database_url(), schema=schema)
    if hasattr(crystals, "open"):
        await crystals.open()
    try:
        async with crystals.connection() as conn:
            await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        await crystals.initialize()
        casino = CasinoStore(crystals)
        await casino.initialize()
        await crystals.import_accounts([Account(123, 100000)], dry_run=False)
        async def lobby():
            if args.optimized:
                await casino.open_panel(123)
            else:
                await casino.recover(123)
                await casino.balance(123)
                await casino.leave(123)
        async def choose(prefs, index):
            if args.optimized:
                snap = await casino.choose_settings(123, prefs.token, base=10 + index % 2 * 10)
                return snap.preferences
            prefs = await casino.choose(123, prefs.token, base=10 + index % 2 * 10)
            await casino.balance(123)
            return prefs
        await lobby()
        timings = {"lobby": [], "choose": []}
        for _ in range(args.samples):
            start = time.perf_counter()
            await lobby()
            timings["lobby"].append((time.perf_counter() - start) * 1000)
        prefs = await casino.settings(123)
        prefs = await choose(prefs, 0)
        for index in range(args.samples):
            start = time.perf_counter()
            prefs = await choose(prefs, index)
            timings["choose"].append((time.perf_counter() - start) * 1000)
        report = {"mode": "optimized" if args.optimized else "baseline", "samples": args.samples,
                  "scope": "isolated schema; warm DB operations; excludes Discord and image upload",
                  "results": {name: {"median_ms": round(statistics.median(values), 2),
                  "p95_ms": round(sorted(values)[math.ceil(.95 * len(values))-1], 2),
                  "samples_ms": [round(v, 2) for v in values]} for name, values in timings.items()}}
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({name: {k:v for k,v in values.items() if k != "samples_ms"}
                          for name, values in report["results"].items()}))
    finally:
        try:
            async with crystals.connection() as conn:
                await conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        finally:
            if hasattr(crystals, "close"):
                await crystals.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optimized", action="store_true")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("Use at least 20 samples")
    configure_event_loop()
    asyncio.run(benchmark(args))
