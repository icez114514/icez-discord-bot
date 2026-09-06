"""Opt-in Neon integration tests; all writes stay in a disposable test schema."""

import asyncio
import os
import re
import unittest
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg import sql

from crystal_commands import CrystalFeature
from database import Account, CrystalStore, DatabaseError, read_database_url
from runtime import configure_event_loop


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "Set RUN_DB_TESTS=1 for isolated Neon tests")
class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        configure_event_loop()

    async def asyncSetUp(self):
        self.schema = "crystal_test_" + uuid.uuid4().hex
        self.store = CrystalStore(read_database_url(), schema=self.schema)
        self.addAsyncCleanup(self.store.close)
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addAsyncCleanup(self.drop_schema)
        await self.store.initialize()

    async def drop_schema(self):
        if not re.fullmatch(r"crystal_test_[0-9a-f]{32}", self.schema):
            raise AssertionError("Refusing to drop a non-test schema.")
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    async def row(self, uid):
        async with self.store.connection(read_only=True) as conn:
            cursor = await conn.execute(sql.SQL(
                "SELECT balance, last_claim_date, display_name FROM {} WHERE user_id = %s"
            ).format(self.store.table), (uid,))
            return await cursor.fetchone()

    async def test_new_account_repeat_and_idempotent_schema(self):
        first = await self.store.claim(123, "first", lambda: 7)
        self.assertEqual((first.balance, first.reward), (17, 7))
        def unexpected_reward():
            raise AssertionError("Repeated claim must not draw a reward")
        repeat = await self.store.claim(123, "updated", unexpected_reward)
        self.assertEqual((repeat.balance, repeat.reward), (17, None))
        await self.store.initialize()
        self.assertEqual((await self.row(123))[0::2], (17, "updated"))
        self.assertTrue(await self.store.check())

    async def test_concurrent_first_claim_across_store_instances(self):
        stores = [CrystalStore(read_database_url(), schema=self.schema) for _ in range(5)]
        for store in stores:
            self.addAsyncCleanup(store.close)
        results = await asyncio.gather(*[
            store.claim(123, "simultaneous", lambda: 7) for store in stores
        ])
        self.assertEqual(sum(r.reward is not None for r in results), 1)
        self.assertEqual({r.balance for r in results}, {17})

    async def test_imported_account_no_newcomer_bonus(self):
        await self.store.import_accounts([Account(123, 100)], dry_run=False)
        self.assertIsNone((await self.row(123))[1])
        result = await self.store.claim(123, "imported", lambda: 7)
        self.assertEqual((result.balance, result.reward), (107, 7))

    async def test_dry_run_and_import_conflict_roll_back_whole_batch(self):
        self.assertEqual(await self.store.import_accounts([Account(123, 100)], dry_run=True), 1)
        self.assertIsNone(await self.row(123))
        await self.store.import_accounts([Account(123, 100)], dry_run=False)
        for dry_run in (True, False):
            with self.assertRaises(DatabaseError):
                await self.store.import_accounts([Account(456, 200), Account(123, 999)], dry_run=dry_run)
            self.assertIsNone(await self.row(456))
            self.assertEqual((await self.row(123))[0], 100)

    async def test_failed_reward_rolls_back(self):
        def failed():
            raise ValueError("Injected failure")
        with self.assertRaises(ValueError):
            await self.store.claim(123, "test", failed)
        self.assertIsNone(await self.row(123))

    async def test_leaderboard_empty_short_ties_and_limit(self):
        self.assertEqual(await self.store.leaderboard(), [])
        await self.store.import_accounts([Account(9, 100), Account(10, 100)], dry_run=False)
        self.assertEqual([a.user_id for a in await self.store.leaderboard()], [9, 10])
        await self.store.import_accounts([
            Account(11, 90), Account(12, 80), Account(13, 70), Account(14, 60),
        ], dry_run=False)
        self.assertEqual([a.user_id for a in await self.store.leaderboard()], [9, 10, 11, 12, 13])

    async def test_taipei_dates_and_claim_after_downtime(self):
        async with self.store.connection() as conn:
            cursor = await conn.execute("""
                SELECT
                  ('2026-09-30 15:59:59+00'::timestamptz AT TIME ZONE 'Asia/Taipei')::date,
                  ('2026-09-30 16:00:00+00'::timestamptz AT TIME ZONE 'Asia/Taipei')::date,
                  ('2026-12-31 16:00:00+00'::timestamptz AT TIME ZONE 'Asia/Taipei')::date
            """)
            self.assertEqual(await cursor.fetchone(), (date(2026, 9, 30), date(2026, 10, 1), date(2027, 1, 1)))
            await conn.execute(sql.SQL("""
                INSERT INTO {} (user_id, balance, last_claim_date)
                VALUES (123, 100, (clock_timestamp() AT TIME ZONE 'Asia/Taipei')::date - 40)
            """).format(self.store.table))
        result = await self.store.claim(123, "returned", lambda: 7)
        self.assertEqual((result.balance, result.reward), (107, 7))
        self.assertIsNone((await self.store.claim(123, "returned", lambda: 7)).reward)

    async def test_cross_entry_and_cross_server_share_daily_claim(self):
        feature = CrystalFeature(self.store)
        low = SimpleNamespace(id=123, display_name="server one", roles=[])
        high = SimpleNamespace(id=123, display_name="server two",
            roles=[SimpleNamespace(id=1, name="LV.150 女武神．愛醬")])
        with patch("crystal_rules.random.random", return_value=0):
            first = await feature.render(low, "daily")
            second = await feature.render(high, "daily")
        self.assertEqual(len(first.fields), 2)
        self.assertEqual(len(second.fields), 1)
        self.assertEqual((await self.row(123))[0], 11)

    async def test_missing_table_has_actionable_error(self):
        empty_schema = "crystal_test_" + uuid.uuid4().hex
        missing = CrystalStore(read_database_url(), schema=empty_schema)
        self.addAsyncCleanup(missing.close)
        with self.assertRaisesRegex(DatabaseError, "database init"):
            await missing.check()

    async def test_numeric_migration_preserves_old_integer_and_is_repeatable(self):
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT crystal_balance_valid").format(self.store.table))
            await conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN balance TYPE BIGINT").format(self.store.table))
            await conn.execute(sql.SQL("INSERT INTO {} (user_id, balance) VALUES (123, 9223372036854775807)").format(self.store.table))
        with self.assertRaisesRegex(DatabaseError, "database migrate"):
            await self.store.check()
        await self.store.migrate()
        await self.store.migrate()
        self.assertTrue(await self.store.check())
        self.assertEqual((await self.row(123))[0], 2**63 - 1)
        self.assertEqual((await self.store.claim(123, "large", lambda: 1)).balance, 2**63)

    async def test_numeric_constraints_and_failed_migration_rollback(self):
        from decimal import Decimal
        for value in (Decimal("-1"), Decimal("0.5"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with self.assertRaises(DatabaseError):
                async with self.store.connection() as conn:
                    await conn.execute(sql.SQL("INSERT INTO {} (user_id, balance) VALUES (123, %s)").format(self.store.table), (value,))
            self.assertIsNone(await self.row(123))
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT crystal_balance_valid").format(self.store.table))
            await conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN balance TYPE BIGINT").format(self.store.table))
            await conn.execute(sql.SQL("INSERT INTO {} (user_id, balance) VALUES (123, -1)").format(self.store.table))
        with self.assertRaises(DatabaseError):
            await self.store.migrate()
        self.assertEqual((await self.row(123))[0], -1)
        with self.assertRaisesRegex(DatabaseError, "database migrate"):
            await self.store.check()

    async def test_huge_import_exact_addition_and_ranking(self):
        huge = 10**100
        await self.store.import_accounts([Account(123, huge), Account(124, huge + 2)], dry_run=False)
        for store in stores:
            self.addAsyncCleanup(store.close)
        results = await asyncio.gather(*[self.store.claim(123, "huge", lambda: 1) for _ in range(3)])
        self.assertEqual(sum(r.reward is not None for r in results), 1)
        self.assertEqual({r.balance for r in results}, {huge + 1})
        self.assertTrue(all(type(r.balance) is int for r in results))
        ranking = await self.store.leaderboard()
        self.assertEqual([a.user_id for a in ranking], [124, 123])
        self.assertEqual(ranking[1].balance, huge + 1)
        self.assertIs(type(ranking[1].balance), int)
