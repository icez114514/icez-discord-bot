"""Redacted local operations and deployment preflight."""
import asyncio
import math
import json
import os
import platform
import shutil
import sqlite3
import sys
import time


def sqlite_fixed(version=None):
    v = sqlite3.sqlite_version_info if version is None else version
    return v >= (3, 51, 3) or (3, 50, 7) <= v < (3, 51, 0) or (3, 44, 6) <= v < (3, 45, 0)


def require_sqlite(config):
    if config.environment == "production" and not sqlite_fixed():
        raise ValueError("SQLite_WAL_fix_required_3_51_3_or_backport_3_50_7_3_44_6")


def preflight(config):
    from .backups import file_hash
    from .npc_worker import EXPECTED, ROOT

    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version, "sqlite_wal_fix": sqlite_fixed(),
        "models": {name: file_hash(ROOT / "data" / name) == digest for name, digest in EXPECTED.items()},
        "static_build": (config.static_dir / "index.html").is_file(),
        "table_admin_count": len(config.table_admins), "funds_admin_count": len(config.funds_admins),
        "phone_acceptance": "not_verified", "oauth_callback": "requires_real_browser",
    }


async def status(app):
    store = app.state.store
    def inspect(db):
        return {
            "maintenance": store.maintenance,
            "frozen_tables": sum(bool(json.loads(row[0]).get("frozen")) for row in db.execute("SELECT state FROM game_tables")),
            "active_hands": db.execute("SELECT COUNT(*) FROM hands WHERE status='active'").fetchone()[0],
            "connections": db.execute("SELECT COUNT(*) FROM presence WHERE until_at>?", (time.time(),)).fetchone()[0],
            "schema": db.execute("PRAGMA user_version").fetchone()[0],
        }
    result = await store.run(inspect)
    samples = sorted(store.latencies)
    commands = sorted(store.command_latencies)
    npc = app.state.npc
    return {
        **result, "backup": app.state.backup, "timing": app.state.timing,
        "process_cpu_seconds": time.process_time(),
        "memory": process_memory(),
        "thermal": phone_thermal(),
        "disk_free_bytes": shutil.disk_usage(store.path.parent).free,
        "database_bytes": store.path.stat().st_size,
        "command_samples": len(commands),
        "command_p95_ms": commands[max(0, math.ceil(len(commands) * .95) - 1)] if commands else None,
        "command_metric": "last_10000_table_create_and_commands_queue_plus_transaction_ms_excludes_network_player_wait_and_npc_inference",
        "writer_samples": len(samples),
        "writer_p95_ms": samples[max(0, math.ceil(len(samples) * .95) - 1)] if samples else None,
        "writer_metric": "last_10000_operations_queue_plus_transaction_ms_includes_reads_and_backups",
        "npc": {"status": npc.status, "requests": npc.requests, "timeouts": npc.timeouts, "failures": npc.failures},
        "pid": os.getpid(), "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
    }


def maintenance(config, enabled):
    marker = config.data_dir / "maintenance"
    if enabled:
        marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker.touch(mode=0o600)
    else:
        marker.unlink(missing_ok=True)


async def monitor_timing(state):
    wall, mono = time.time(), time.monotonic()
    while True:
        await asyncio.sleep(1)
        next_wall, next_mono = time.time(), time.monotonic()
        elapsed = next_mono - mono
        state["max_loop_delay_ms"] = max(state["max_loop_delay_ms"], max(0, elapsed - 1) * 1000)
        state["max_wall_clock_step_ms"] = max(state["max_wall_clock_step_ms"], abs(next_wall - wall - elapsed) * 1000)
        wall, mono = next_wall, next_mono


def process_memory():
    # Linux/Android report current RSS; unsupported platforms are explicitly unknown.
    try:
        from pathlib import Path
        fields = Path("/proc/self/status").read_text().splitlines()
        return {"rss_kib": next(int(line.split()[1]) for line in fields if line.startswith("VmRSS:"))}
    except (OSError, StopIteration, ValueError):
        return {"rss_kib": None}


def phone_thermal():
    from pathlib import Path
    result = {}
    for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
        try:
            result[zone.name] = {"type": (zone / "type").read_text().strip()[:80],
                                 "millidegrees_c": int((zone / "temp").read_text().strip())}
        except (OSError, ValueError):
            continue
    return result
