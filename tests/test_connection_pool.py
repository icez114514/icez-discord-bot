"""Pool contracts using a disposable PostgreSQL schema."""
import asyncio
import os
import unittest
from uuid import uuid4
from psycopg import sql
from psycopg.rows import dict_row
from database import CrystalStore, DatabaseError, read_database_url
from runtime import configure_event_loop

@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "Isolated PostgreSQL tests are opt-in")
class PoolTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        configure_event_loop()

    async def asyncSetUp(self):
        self.store = CrystalStore(read_database_url(), schema="casino_test_" + uuid4().hex)
        self.addAsyncCleanup(self.store.close)
        await self.store.open()

    async def test_reuse_resets_row_factory_and_read_only(self):
        async with self.store.connection(read_only=True) as conn:
            first = conn
            conn.row_factory = dict_row
            self.assertEqual(await (await conn.execute("SELECT 7 AS value")).fetchone(), {"value": 7})
        async with self.store.connection() as conn:
            self.assertIs(conn, first)
            self.assertEqual(await (await conn.execute("SELECT 8")).fetchone(), (8,))
            self.assertEqual(await (await conn.execute("SHOW transaction_read_only")).fetchone(), ("off",))
            self.assertEqual(await (await conn.execute("SHOW statement_timeout")).fetchone(), ("10s",))
            self.assertEqual(await (await conn.execute("SHOW lock_timeout")).fetchone(), ("5s",))
        await self.store.close()
        await self.store.close()
        with self.assertRaises(DatabaseError):
            async with self.store.connection():
                pass

    async def test_cancel_rolls_back_and_connection_recovers(self):
        schema = self.store.schema
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        async def cleanup():
            async with self.store.connection() as conn:
                await conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        self.addAsyncCleanup(cleanup)
        await self.store.initialize()
        from database import Account
        await self.store.import_accounts([Account(123, 10)], dry_run=False)
        ready = asyncio.Event()
        async def interrupted():
            async with self.store.connection() as conn:
                await conn.execute(sql.SQL("UPDATE {} SET balance=99").format(self.store.table))
                ready.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(interrupted())
        await ready.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual((await self.store.leaderboard())[0].balance, 10)
        await self.store.claim(123, 'test', lambda: 7)
        self.assertEqual((await self.store.leaderboard())[0].balance, 17)

    async def test_closed_connection_is_replaced(self):
        async with self.store.connection() as conn:
            old = conn
        await old.close()
        with self.assertRaises(DatabaseError):
            async with self.store.connection() as conn:
                await conn.execute("SELECT 1")
        async with self.store.connection() as conn:
            self.assertIsNot(conn, old)
            self.assertEqual(await (await conn.execute("SELECT 1")).fetchone(), (1,))

    async def test_exhaustion_has_bounded_wait_and_releases_capacity(self):
        from contextlib import AsyncExitStack
        from database import DatabaseBusy
        async with AsyncExitStack() as stack:
            for _ in range(4):
                await stack.enter_async_context(self.store.connection())
            start = asyncio.get_running_loop().time()
            with self.assertRaises(DatabaseBusy):
                async with self.store.connection():
                    pass
            self.assertLess(asyncio.get_running_loop().time() - start, 7)
        async with self.store.connection() as conn:
            self.assertEqual(await (await conn.execute("SELECT 1")).fetchone(), (1,))
