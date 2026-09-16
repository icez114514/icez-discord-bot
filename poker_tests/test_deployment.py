import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from poker.backups import file_hash, inspect_snapshot, restore, retain, take_backup
from poker.config import Config, load_environment
from poker.encryption import transform
from poker.operations import sqlite_fixed
from poker.store import Store


class BackupTests(unittest.IsolatedAsyncioTestCase):
    async def test_wal_restore_preserves_sessions_ledger_and_idempotency(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            async with Store(root / "live/poker.db", initialize=True) as store:
                token = await store.login("111")
                await store.command("debit", "adjust", user_id="111", amount="-123", actor="999", reason="drill")
                account, ledger = await store.account("111"), await store.ledger("111")
                result = await take_backup(store, root / "snapshots")
                source = root / "snapshots" / result["file"]
                self.assertEqual(inspect_snapshot(source)["schema"], 4)
                self.assertEqual(result["sha256"], file_hash(source))
                restore(source, root / "restored", result["sha256"])
                async with Store(root / "restored/poker.db") as recovered:
                    self.assertTrue(recovered.maintenance)
                    self.assertEqual(await recovered.authenticate(token), "111")
                    self.assertEqual(await recovered.account("111"), account)
                    await recovered.command("debit", "adjust", user_id="111", amount="-123", actor="999", reason="drill")
                    self.assertEqual(await recovered.ledger("111"), ledger)
                with self.assertRaises(ValueError):
                    restore(source, root / "restored", result["sha256"])
                with self.assertRaises(ValueError):
                    restore(source, root / "wrong", "0" * 64)
                with self.assertRaises(RuntimeError):
                    restore(source, root / "live", result["sha256"])

    async def test_concurrent_writes_snapshot_is_consistent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            async with Store(root / "live/poker.db", initialize=True) as store:
                await store.login("111")
                writes = [store.command(str(i), "adjust", user_id="111", amount="-1", actor="999", reason="drill") for i in range(25)]
                results = await asyncio.gather(*writes, take_backup(store, root / "snapshots"))
                backup = results[-1]
                async with Store(root / "snapshots" / backup["file"]) as copied:
                    self.assertEqual((await copied.account("111"))["available"], "49975")

    async def test_encryption_rejects_wrong_password_and_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            async with Store(root / "live/poker.db", initialize=True) as store:
                await store.login("111")
                result = await take_backup(store, root / "snapshots")
            source = root / "snapshots" / result["file"]
            encrypted, plaintext = root / "export.enc", root / "decrypted.db"
            transform(source, encrypted, "correct horse battery staple")
            self.assertNotIn(b"SQLite format", encrypted.read_bytes())
            transform(encrypted, plaintext, "correct horse battery staple", True)
            self.assertEqual(file_hash(source), file_hash(plaintext))
            with self.assertRaises(ValueError):
                transform(encrypted, root / "wrong.db", "wrong password long enough", True)
            self.assertFalse((root / "wrong.db").exists())
            data = bytearray(encrypted.read_bytes())
            data[-20] ^= 1
            encrypted.write_bytes(data)
            with self.assertRaises(ValueError):
                transform(encrypted, root / "tampered.db", "correct horse battery staple", True)
            self.assertFalse((root / "tampered.db").exists())
            self.assertEqual(list(root.glob("*.partial")), [])

    async def test_corruption_and_unreconciled_ledger_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            broken = root / "broken.db"
            broken.write_bytes(b"not a database")
            with self.assertRaises(sqlite3.Error):
                inspect_snapshot(broken)
            async with Store(root / "live/poker.db", initialize=True) as store:
                await store.login("111")
                await store.run(lambda db: db.execute("UPDATE accounts SET available=1"))
                with self.assertRaisesRegex(ValueError, "ledger_mismatch"):
                    await take_backup(store, root / "snapshots")
            self.assertEqual(list((root / "snapshots").glob("snapshot-*.db")), [])

    async def test_failed_backup_keeps_previous_snapshot(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            async with Store(root / "live/poker.db", initialize=True) as store:
                await store.login("111")
                first = await take_backup(store, root / "snapshots")
                with patch("os.fsync", side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        await take_backup(store, root / "snapshots")
                self.assertEqual(file_hash(root / "snapshots" / first["file"]), first["sha256"])
                self.assertEqual(len(list((root / "snapshots").glob("snapshot-*.db"))), 1)

    async def test_migration_backs_up_and_leaves_maintenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            async with Store(root / "live/poker.db", initialize=True) as store:
                await store.login("111")
            before = root / "upgrade.db"
            async with Store(root / "live/poker.db", initialize=True, migration_backup=before) as store:
                self.assertTrue(store.maintenance)
                self.assertEqual((await store.account("111"))["available"], "50000")
            self.assertEqual(inspect_snapshot(before)["schema"], 4)


class DeploymentConfigTests(unittest.TestCase):
    def test_shared_bom_env_and_explicit_overrides_without_interpolation(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"POKER_CLIENT_ID": "789", "USERPROFILE": folder, "HOME": folder}, clear=True):
            env = Path(folder) / ".env"
            secret = "literal$" + "{TOKEN}long"
            env.write_text("APPLICATION_ID=123\nCLIENT_SECRET=" + secret + "\nDISCORD_TOKEN=bot-secret-value-long\nDISCORD_GUILD_ID=456\n", encoding="utf-8-sig")
            load_environment(env)
            config = Config.from_env()
            self.assertEqual(config.client_id, "789")
            self.assertEqual(config.guild_id, "456")
            self.assertEqual(config.client_secret, secret)
            self.assertEqual(config.bot_token, "bot-secret-value-long")
            self.assertNotIn(config.client_secret, repr(config))

    def test_retention_preserves_recent_24h_seven_daily_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = time.time()
            recent, old = root / "snapshot-recent.db", root / "snapshot-old.db"
            recent.touch()
            old.touch()
            os.utime(old, (now - 90000, now - 90000))
            for day in range(1, 10):
                (root / f"daily-2026-09-{day:02}.db").touch()
            unrelated = root / "upgrade-manual.db"
            unrelated.touch()
            retain(root, now)
            self.assertTrue(recent.exists())
            self.assertFalse(old.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(len(list(root.glob("daily-*.db"))), 7)

    def test_sqlite_release_gate(self):
        self.assertFalse(sqlite_fixed((3, 37, 2)))
        self.assertFalse(sqlite_fixed((3, 51, 2)))
        self.assertTrue(sqlite_fixed((3, 51, 3)))
        self.assertTrue(sqlite_fixed((3, 50, 7)))
        self.assertTrue(sqlite_fixed((3, 44, 6)))
