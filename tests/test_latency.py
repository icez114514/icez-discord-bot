"""Latency scopes preserve cancellation and isolate concurrent operations."""
import asyncio
import unittest
from unittest.mock import patch, AsyncMock
from latency import operation, measure, measured_lock, correlation_id, mark_cold, mark_action
from database import CrystalStore, DatabaseError
from psycopg_pool import PoolTimeout

class LatencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_scopes_are_isolated_and_do_not_log_arguments(self):
        seen = []
        @operation('test')
        async def task(secret):
            mark_cold()
            mark_action("base:" + secret)
            with measure('db_ms'):
                await asyncio.sleep(0)
            seen.append(correlation_id())
        with self.assertLogs(level='INFO') as logs:
            await asyncio.gather(task('SECRET_SENTINEL'), task('OTHER_SECRET'))
        self.assertEqual(len(set(seen)), 2)
        self.assertEqual(correlation_id(), '-')
        text = ' '.join(logs.output)
        self.assertNotIn('SECRET', text)
        self.assertIn('action=base', text)
        for field in ('pool_wait_ms=', 'db_ms=', 'owner_wait_ms=', 'compose_ms=', 'update_ms=', 'auth_ms=', 'total_ms=', 'connection=cold'):
            self.assertIn(field, text)

    async def test_cancelled_wait_does_not_release_someone_elses_lock(self):
        lock = asyncio.Lock()
        entered = asyncio.Event()
        @operation('cancel')
        async def wait():
            entered.set()
            async with measured_lock(lock):
                self.fail('Cancelled waiter acquired lock')
        await lock.acquire()
        with self.assertLogs(level='INFO') as logs:
            task = asyncio.create_task(wait())
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(lock.locked())
        lock.release()
        self.assertIn('status=cancelled', ' '.join(logs.output))

    async def test_startup_failure_closes_pool_without_exposing_driver_error(self):
        store = CrystalStore('postgresql://unused:secret@example.invalid/db')
        with patch.object(store._pool, 'open', new=AsyncMock(side_effect=PoolTimeout('SECRET_SENTINEL'))), patch.object(store._pool, 'close', new=AsyncMock()) as close:
            with self.assertRaises(DatabaseError) as error:
                await store.open()
            close.assert_awaited_once()
            self.assertNotIn('SECRET', str(error.exception))
            self.assertTrue(store._closed)

    async def test_discord_delivery_and_handled_failure_are_measured(self):
        from latency import discord_update, mark_status
        @operation('delivery')
        async def send():
            await discord_update(asyncio.sleep(0.02))
            mark_status('busy')
        with self.assertLogs(level='INFO') as logs:
            await send()
        text = ' '.join(logs.output)
        self.assertIn('status=busy', text)
        import re
        self.assertGreater(float(re.search(r'update_ms=([0-9.]+)', text)[1]), 10)

    async def test_database_startup_has_cold_correlation(self):
        from bot import prepare_database
        store = AsyncMock()
        with patch('bot.CasinoStore') as casino, self.assertLogs(level='INFO') as logs:
            casino.return_value.check = AsyncMock()
            await prepare_database(store)
        self.assertIn('operation=bot.database_startup connection=cold', ' '.join(logs.output))

    async def test_bot_closes_store_when_startup_check_fails(self):
        import bot
        store = AsyncMock()
        with patch.object(bot, 'read_database_url', return_value='unused'), patch.object(bot, 'CrystalStore', return_value=store), patch.object(bot, 'prepare_database', new=AsyncMock(side_effect=DatabaseError('unavailable'))):
            with self.assertRaises(DatabaseError):
                await bot.main('unused', None)
        store.close.assert_awaited_once()
