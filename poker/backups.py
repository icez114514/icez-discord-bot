"""SQLite backup API snapshots with private retention and non-destructive restore."""
import asyncio
import contextlib
import hashlib
import logging
import os
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from .locking import ProcessLock

log = logging.getLogger("poker.backup")


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("backup_directory_symlink_rejected")
    if os.name != "nt":
        path.chmod(0o700)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_snapshot(path):
    """Immutable reads are only for closed standalone snapshots, never a live DB."""
    if not path.is_file() or path.is_symlink():
        raise ValueError("snapshot_file_required")
    if any(path.with_name(path.name + s).exists() for s in ("-wal", "-shm")):
        raise ValueError("standalone_snapshot_required")
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("snapshot_integrity_failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("snapshot_foreign_keys_failed")
        schema = db.execute("PRAGMA user_version").fetchone()[0]
        if schema not in (1, 2, 3, 4):
            raise ValueError("snapshot_schema_unsupported")
        mismatch = db.execute("""
            SELECT 1 FROM accounts a LEFT JOIN (
              SELECT user_id,SUM(available_delta) av,SUM(table_delta) tb,
                     SUM(flight_delta) fl,SUM(settled_delta) st
              FROM ledger GROUP BY user_id
            ) l USING(user_id)
            WHERE a.available != COALESCE(l.av,0) OR a.table_chips != COALESCE(l.tb,0)
               OR a.in_flight != COALESCE(l.fl,0) OR a.settled != COALESCE(l.st,0)
            LIMIT 1
        """).fetchone()
        if mismatch:
            raise ValueError("snapshot_ledger_mismatch_investigate")
        return {"schema": schema, "active_hands": db.execute("SELECT COUNT(*) FROM hands WHERE status='active'").fetchone()[0]}


def snapshot(db, destination):
    """Run on the writer outside a transaction; backup includes committed WAL data."""
    private_directory(destination.parent)
    if destination.exists():
        raise ValueError("snapshot_destination_exists")
    temporary = destination.with_name("." + uuid.uuid4().hex + ".partial")
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with contextlib.closing(sqlite3.connect(temporary)) as target:
            db.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
        info = inspect_snapshot(temporary)
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        temporary.replace(destination)
        return {**info, "sha256": file_hash(destination)}
    finally:
        temporary.unlink(missing_ok=True)


def retain(directory, now):
    for path in directory.glob("snapshot-*.db"):
        if path.stat().st_mtime < now - 86400:
            path.unlink()
    for path in sorted(directory.glob("daily-????-??-??.db"), reverse=True)[7:]:
        path.unlink()


async def take_backup(store, directory):
    def work(db):
        private_directory(directory)
        lock = ProcessLock(directory / "backup.lock")
        lock.acquire()
        try:
            now = time.time()
            stamp = datetime.fromtimestamp(now, timezone.utc)
            target = directory / ("snapshot-" + stamp.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".db")
            info = snapshot(db, target)
            daily = directory / ("daily-" + stamp.strftime("%Y-%m-%d") + ".db")
            if not daily.exists():
                # Copy a closed snapshot, never copy the live database.
                partial = daily.with_suffix(".partial")
                try:
                    with target.open("rb") as src, partial.open("wb") as dst:
                        os.chmod(partial, 0o600)
                        shutil.copyfileobj(src, dst)
                        dst.flush()
                        os.fsync(dst.fileno())
                    partial.replace(daily)
                finally:
                    partial.unlink(missing_ok=True)
            retain(directory, now)
            return {**info, "file": target.name, "completed_at": time.time()}
        finally:
            lock.release()
    return await store.run(work, transaction=False)


async def schedule(store, directory, state):
    while True:
        started = time.monotonic()
        delay = 900.0
        try:
            state.update(await take_backup(store, directory), error=None)
        except Exception as error:
            state["error"] = type(error).__name__
            log.error("snapshot_failed type=%s", type(error).__name__)
            delay = 60.0
        await asyncio.sleep(max(1, delay - (time.monotonic() - started)))


def restore(source, destination, expected_hash):
    """Refuse existing DB/WAL files; leave restored service in maintenance mode."""
    if file_hash(source) != expected_hash:
        raise ValueError("snapshot_hash_mismatch")
    inspect_snapshot(source)
    private_directory(destination)
    lock = ProcessLock(destination / "poker.lock")
    lock.acquire()
    try:
        if any((destination / name).exists() for name in ("poker.db", "poker.db-wal", "poker.db-shm")):
            raise ValueError("restore_requires_empty_data_directory")
        (destination / "maintenance").touch(mode=0o600)
        with contextlib.closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            return snapshot(db, destination / "poker.db")
    finally:
        lock.release()
