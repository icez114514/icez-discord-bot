"""Casino contracts against disposable PostgreSQL schemas, never public tables."""

import asyncio
import os
import re
import unittest
import uuid

from psycopg import sql

from casino_store import CasinoStore
from casino_rules import CasinoError
from database import Account, CrystalStore, read_database_url
from runtime import configure_event_loop


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "Set RUN_DB_TESTS=1 for isolated PostgreSQL tests")
class CasinoDatabaseTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        configure_event_loop()

    async def asyncSetUp(self):
        self.schema = "casino_test_" + uuid.uuid4().hex
        self.crystals = CrystalStore(read_database_url(), schema=self.schema)
        self.addAsyncCleanup(self.crystals.close)
        async with self.crystals.connection() as conn:
            await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addAsyncCleanup(self.drop_schema)
        await self.crystals.initialize()
        await self.crystals.import_accounts([Account(123, 1000)], dry_run=False)
        self.casino = CasinoStore(self.crystals, roll=lambda: (6, 6, 6, 1, 2, 3))
        await self.casino.initialize()

    async def drop_schema(self):
        if not re.fullmatch(r"casino_test_[0-9a-f]{32}", self.schema):
            raise AssertionError("Refusing to drop non-test schema")
        async with self.crystals.connection() as conn:
            await conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    async def test_cancel_during_batched_debit_rolls_back_and_keeps_token(self):
        prefs = await self.casino.settings(123)
        execute = self.casino.execute
        ready = asyncio.Event()
        async def paused(conn, query, params=()):
            if 'UPDATE {preferences} SET token=NULL' in query:
                ready.set()
                await asyncio.Event().wait()
            return await execute(conn, query, params)
        self.casino.execute = paused
        pending = asyncio.create_task(self.casino.start(123, prefs.token))
        try:
            await asyncio.wait_for(ready.wait(), 10)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            self.casino.execute = execute
        self.assertEqual(await self.casino.balance(123), 1000)
        self.assertEqual((await self.casino.preferences(123)).token, prefs.token)
        self.assertIsNone(await self.casino.recover(123))

    async def test_pipeline_error_rolls_back_all_debit_writes_and_reuses_connection(self):
        from database import DatabaseError
        prefs = await self.casino.settings(123)
        execute = self.casino.execute
        async def fail_after_stake(conn, query, params=()):
            if 'UPDATE {preferences} SET token=NULL' in query:
                return await conn.execute('SELECT 1/0')
            return await execute(conn, query, params)
        self.casino.execute = fail_after_stake
        try:
            with self.assertRaises(DatabaseError):
                await self.casino.start(123, prefs.token)
        finally:
            self.casino.execute = execute
        self.assertEqual(await self.casino.balance(123), 1000)
        self.assertEqual((await self.casino.preferences(123)).token, prefs.token)
        self.assertIsNone(await self.casino.recover(123))
        game = await self.casino.start(123, prefs.token)
        self.assertEqual(len(await self.casino.ledger(123, game.id)), 2)

    async def test_panel_cannot_leave_active_game_with_old_sources(self):
        cards = [4, 8, 5, 20] + [c for c in range(52) if c not in (4, 8, 5, 20)]
        casino = CasinoStore(self.crystals, deck=lambda: cards)
        settings = await casino.open_panel(123, settings=True)
        game = await casino.start(123, settings.preferences.token, game='blackjack')
        self.assertEqual(game.status, 'active')
        for destination in (False, True):
            for source in ({'game_id': game.id}, {'token': settings.preferences.token}):
                with self.assertRaises(CasinoError):
                    await casino.open_panel(123, settings=destination, **source)
        self.assertEqual(await casino.open_panel(123), game)
        self.assertEqual(len(await casino.ledger(123, game.id)), 1)

    async def test_panel_transition_commit_failure_does_not_partially_dismiss(self):
        from contextlib import asynccontextmanager
        from database import DatabaseError
        prefs = await self.casino.settings(123)
        game = await self.casino.start(123, prefs.token)
        original = self.crystals.connection
        @asynccontextmanager
        async def fail(**kwargs):
            async with original(**kwargs) as conn:
                yield conn
                raise DatabaseError('Injected pre-commit failure')
        self.crystals.connection = fail
        try:
            with self.assertRaises(DatabaseError):
                await self.casino.open_panel(123, settings=True, game_id=game.id)
        finally:
            self.crystals.connection = original
        self.assertEqual(await self.casino.open_panel(123), game)
        self.assertEqual(len(await self.casino.ledger(123, game.id)), 2)

    async def test_panel_snapshots_and_transitions_are_atomic(self):
        from casino_store import LobbySnapshot, SettingsSnapshot
        lobby = await self.casino.open_panel(123)
        self.assertEqual(lobby, LobbySnapshot(1000))
        self.assertEqual(await self.casino.open_panel(999), LobbySnapshot(None))
        settings = await self.casino.open_panel(123, settings=True)
        self.assertIsInstance(settings, SettingsSnapshot)
        await self.crystals.claim(123, 'name', lambda: 7)
        changed = await self.casino.choose_settings(123, settings.preferences.token, base=246, custom=True)
        self.assertEqual((changed.balance, changed.preferences.custom_base), (1007, 246))
        with self.assertRaises(CasinoError):
            await self.casino.open_panel(123, token=settings.preferences.token)
        game = await self.casino.start(123, changed.preferences.token)
        self.assertEqual((await self.casino.open_panel(123)).id, game.id)
        adjusted = await self.casino.open_panel(123, settings=True, game_id=game.id)
        self.assertEqual(adjusted.balance, game.balance_after)
        with self.assertRaises(CasinoError):
            await self.casino.replay(123, game.id)
        await self.casino.open_panel(123, token=adjusted.preferences.token)
        with self.assertRaises(CasinoError):
            await self.casino.start(123, adjusted.preferences.token)

    async def test_panel_uses_one_checkout_and_returns_it_before_delivery(self):
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock
        from casino_commands import CasinoFeature
        from types import SimpleNamespace
        original = self.crystals.connection
        calls, held = [], []
        @asynccontextmanager
        async def counted(**kwargs):
            calls.append(kwargs)
            async with original(**kwargs) as conn:
                held.append(conn)
                try:
                    yield conn
                finally:
                    held.pop()
        self.crystals.connection = counted
        panel = await self.casino.open_panel(123, settings=True)
        self.assertEqual(len(calls), 1)
        panel = await self.casino.choose_settings(123, panel.preferences.token, base=20)
        self.assertEqual(len(calls), 2)
        feature = CasinoFeature(self.casino)
        async def deliver(*args, **kwargs):
            self.assertFalse(held)
            self.assertEqual(len(calls), 2)
        feature.render = AsyncMock(side_effect=deliver)
        await feature.show_settings(SimpleNamespace(user=SimpleNamespace(id=123)), panel)

    async def test_win_persists_exact_balance_result_and_ledger(self):
        prefs = await self.casino.settings(123)
        prefs = await self.casino.choose(123, prefs.token, base=100)
        game = await self.casino.start(123, prefs.token)
        self.assertEqual((game.status, game.wager, game.returned, game.net), ("settled", 100, 200, 100))
        restarted = CasinoStore(self.crystals)
        self.assertEqual((await restarted.recover(123)).id, game.id)
        self.assertEqual(await restarted.balance(123), 1100)
        self.assertEqual([(e.kind, e.amount, e.before, e.after) for e in await restarted.ledger(123, game.id)],
                         [("stake", -100, 1000, 900), ("payout", 200, 900, 1100)])


    async def test_replay_is_one_successor_even_after_instant_settlement(self):
        prefs = await self.casino.settings(123)
        game = await self.casino.start(123, prefs.token)
        other = CasinoStore(self.crystals, roll=lambda: (1, 2, 3, 6, 6, 6))
        children = await asyncio.gather(self.casino.replay(123, game.id), other.replay(123, game.id))
        self.assertEqual(children[0].id, children[1].id)
        again = await other.replay(123, game.id)
        self.assertEqual(again.id, children[0].id)
        self.assertEqual(len(await other.ledger(123, again.id)), 2)
        self.assertEqual(await other.balance(123), 1000 + game.net + again.net)

    async def test_preferences_survive_fixed_choices_restart_and_repeat_migration(self):
        before = await self.crystals.claim(123, 'name', lambda: 7)
        prefs = await self.casino.settings(123)
        prefs = await self.casino.choose(123, prefs.token, base=246, custom=True)
        prefs = await self.casino.choose(123, prefs.token, multiplier=13, custom=True)
        prefs = await self.casino.choose(123, prefs.token, base=50, multiplier=2)
        for value in (0, 1, 3, -2, 2.0, True):
            with self.assertRaises(CasinoError):
                await self.casino.choose(123, prefs.token, base=value, custom=True)
        restarted = CasinoStore(self.crystals)
        await restarted.initialize()
        await restarted.initialize()
        saved = await restarted.preferences(123)
        self.assertEqual((saved.bet.base, saved.bet.multiplier, saved.custom_base, saved.custom_multiplier), (50, 2, 246, 13))
        self.assertEqual((await self.crystals.claim(123, 'name', lambda: 100)).balance, before.balance)

    async def test_corrupt_unfinished_dice_refund_once_and_leave_cancels_replay(self):
        from contextlib import asynccontextmanager
        original = self.crystals.connection

        @asynccontextmanager
        async def interrupted_connection(**kwargs):
            async with original(**kwargs) as conn:
                yield conn
            raise SystemExit('Simulated process death after debit COMMIT')

        prefs = await self.casino.settings(123)
        self.crystals.connection = interrupted_connection
        with self.assertRaises(SystemExit):
            await self.casino.start(123, prefs.token)
        self.crystals.connection = original
        self.assertEqual(await self.casino.balance(123), 990)
        async with original() as conn:
            await conn.execute(sql.SQL("UPDATE {} SET dice='[0]'::jsonb WHERE user_id=123").format(sql.Identifier(self.schema, 'casino_games')))
        recovered = await self.casino.recover(123)
        self.assertEqual((recovered.status, recovered.returned, recovered.net), ('void', 10, 0))
        self.assertEqual((await self.casino.recover(123)).id, recovered.id)
        self.assertEqual(await self.casino.balance(123), 1000)
        self.assertEqual([(e.kind, e.amount) for e in await self.casino.ledger(123, recovered.id)], [('stake', -10), ('refund', 10)])
        await self.casino.leave(123, game_id=recovered.id)
        self.assertIsNone(await self.casino.recover(123))
        with self.assertRaises(CasinoError):
            await self.casino.replay(123, recovered.id)


    async def test_discord_full_flow_preferences_and_delivery_failure_recovery(self):
        from casino_commands import CasinoFeature, BetModal, ResultView
        from test_casino_ui import interaction
        import discord

        feature = CasinoFeature(self.casino)
        feature.dealer_path = 'missing-placeholder'
        event = interaction()
        await feature.slash(event)
        lobby = event.edit_original_response.call_args.kwargs['view']
        self.assertFalse(event.response.defer.call_args.kwargs.get('ephemeral', False))
        await feature.act(event, lobby, 'settings')
        settings = event.edit_original_response.call_args.kwargs['view']
        modal = BetModal(settings, 'base')
        modal.amount._value = '246'
        await modal.on_submit(event)
        settings = event.edit_original_response.call_args.kwargs['view']
        self.assertEqual(settings.prefs.bet.total, 246)
        self.assertEqual(await self.casino.balance(123), 1000)
        await feature.act(event, settings, 'base:100')
        settings = event.edit_original_response.call_args.kwargs['view']
        await feature.act(event, settings, 'start')
        result = event.edit_original_response.call_args.kwargs['view']
        self.assertIsInstance(result, ResultView)
        self.assertEqual([b.label for b in result.children], ['再來一局', '修改下注', '返回大廳'])
        self.assertEqual(await self.casino.balance(123), 1100)
        denied = interaction(456)
        await feature.act(denied, result, 'replay')
        self.assertTrue(denied.response.send_message.call_args.kwargs['ephemeral'])
        self.assertEqual(await self.casino.balance(123), 1100)
        failure = discord.HTTPException(type('Response', (), {'status': 500, 'reason': 'test'})(), 'delivery failed')
        event.edit_original_response.side_effect = failure
        await feature.act(event, result, 'replay')
        self.assertEqual(await self.casino.balance(123), 1200)
        event.edit_original_response.side_effect = None
        await feature.slash(event)
        recovered = event.edit_original_response.call_args.kwargs['view']
        self.assertNotEqual(recovered.game.id, result.game.id)
        await feature.act(event, result, 'replay')
        self.assertEqual(await self.casino.balance(123), 1200)
        await feature.act(event, recovered, 'settings')
        settings = event.edit_original_response.call_args.kwargs['view']
        self.assertEqual(BetModal(settings, 'base').amount.default, '246')
        await feature.act(event, settings, 'lobby')
        self.assertEqual(await self.casino.balance(123), 1200)
        self.assertIsNone(await self.casino.recover(123))
        await feature.act(event, settings, 'start')
        self.assertTrue(event.followup.send.call_args.kwargs['ephemeral'])
        self.assertEqual(await self.casino.balance(123), 1200)

    async def test_concurrent_claim_and_start_retries_use_one_exact_wager(self):
        huge = 10**100
        await self.crystals.import_accounts([Account(124, huge)], dry_run=False)
        prefs = await self.casino.settings(124)
        prefs = await self.casino.choose(124, prefs.token, base=huge, multiplier=1, custom=True)
        stores = [CasinoStore(CrystalStore(read_database_url(), schema=self.schema),
                              roll=lambda: (1, 2, 3, 6, 6, 6)) for _ in range(3)]
        for store in stores:
            self.addAsyncCleanup(store.crystals.close)
        results = await asyncio.gather(*(s.start(124, prefs.token) for s in stores),
                                      self.crystals.claim(124, 'daily', lambda: 7))
        self.assertEqual(len({g.id for g in results[:3]}), 1)
        self.assertEqual(await self.casino.balance(124), 7)
        self.assertEqual([(e.kind, e.amount) for e in await self.casino.ledger(124, results[0].id)],
                         [('stake', -huge), ('payout', 0)])

    async def test_reject_no_account_insufficient_blackjack_and_stale_preferences(self):
        with self.assertRaises(CasinoError):
            await self.casino.settings(999)
        prefs = await self.casino.settings(123)
        newer = await self.casino.choose(123, prefs.token, base=2000)
        with self.assertRaises(CasinoError):
            await self.casino.start(123, prefs.token)
        with self.assertRaises(CasinoError):
            await self.casino.start(123, newer.token)
        with self.assertRaises(CasinoError):
            await self.casino.start(123, newer.token, game='blackjack')
        self.assertEqual(await self.casino.balance(123), 1000)
        self.assertIsNone(await self.casino.recover(123))

    async def test_dice_ranking_and_same_grade_sum_through_settlement(self):
        cases = [
            ((1,1,1,4,5,6), 'win'),
            ((4,5,6,6,6,5), 'win'),
            ((2,2,1,1,2,3), 'win'),
            ((1,2,3,3,5,6), 'win'),
            ((2,2,5,6,6,4), 'win'),
            ((6,6,5,1,1,5), 'win'),
            ((1,1,1,2,2,2), 'loss'),
            ((1,3,5,1,2,6), 'tie'),
            ((1,3,4,2,4,6), 'loss'),
        ]
        for dice, expected in cases:
            with self.subTest(dice=dice):
                self.casino.roll = lambda: dice
                prefs = await self.casino.settings(123)
                prefs = await self.casino.choose(123, prefs.token, base=100)
                previous = await self.casino.balance(123)
                game = await self.casino.start(123, prefs.token)
                self.assertEqual(game.outcome, expected)
                self.assertEqual(game.net, {'win': 100, 'loss': -100, 'tie': 0}[expected])
                self.assertEqual(await self.casino.balance(123), previous + game.net)
                await self.casino.leave(123, game_id=game.id)


    async def test_commit_interruptions_preserve_money_and_active_cross_store_lock(self):
        from contextlib import asynccontextmanager
        from database import DatabaseError

        # Faults surround real PostgreSQL commits, not a mocked money store.
        for transaction, phase, crash in [(1, 'before', False), (1, 'after', False),
                                          (2, 'before', False), (2, 'after', False),
                                          (1, 'after', True), (2, 'after', True)]:
            with self.subTest(transaction=transaction, phase=phase, crash=crash):
                prefs = await self.casino.settings(123)
                before = await self.casino.balance(123)
                original = self.crystals.connection
                count = 0

                @asynccontextmanager
                async def faulty_connection(**kwargs):
                    nonlocal count
                    count += 1
                    inject = count == transaction
                    async with original(**kwargs) as conn:
                        yield conn
                        if inject and phase == 'before':
                            raise DatabaseError('Injected failure before COMMIT')
                    if inject and phase == 'after':
                        if crash:
                            raise SystemExit('Simulated process exit')
                        raise DatabaseError('Lost COMMIT acknowledgement')

                self.crystals.connection = faulty_connection
                try:
                    try:
                        await self.casino.start(123, prefs.token)
                    except (DatabaseError, SystemExit):
                        pass
                finally:
                    self.crystals.connection = original

                other = CasinoStore(CrystalStore(read_database_url(), schema=self.schema),
                                    roll=lambda: (_ for _ in ()).throw(AssertionError('Recovery must not reroll')))
                self.addAsyncCleanup(other.crystals.close)
                if transaction == 1 and phase == 'before':
                    self.assertIsNone(await other.recover(123))
                    self.assertEqual(await other.balance(123), before)
                    continue
                if (transaction == 1 and crash) or (transaction == 2 and phase == 'before'):
                    self.assertEqual(await other.balance(123), before - 10)
                    with self.assertRaises(CasinoError):
                        await other.settings(123)
                    with self.assertRaises(CasinoError):
                        await other.start(123, uuid.uuid4())
                    with self.assertRaises(CasinoError):
                        await other.leave(123)
                game = await other.recover(123)
                self.assertEqual((game.status, game.net), ('settled', 10))
                self.assertEqual(await other.balance(123), before + 10)
                self.assertEqual(len(await other.ledger(123, game.id)), 2)
                self.assertEqual((await other.start(123, prefs.token)).id, game.id)
                self.assertEqual(await other.balance(123), before + 10)
                await other.leave(123, game_id=game.id)


    async def test_binary_backup_restore_recovers_inflight_game_and_ledger(self):
        from contextlib import asynccontextmanager
        original = self.crystals.connection

        @asynccontextmanager
        async def crash_after_commit(**kwargs):
            async with original(**kwargs) as conn:
                yield conn
            raise SystemExit('Simulated process death')

        prefs = await self.casino.settings(123)
        self.crystals.connection = crash_after_commit
        try:
            with self.assertRaises(SystemExit):
                await self.casino.start(123, prefs.token)
        finally:
            self.crystals.connection = original
        tables = ('crystal_accounts', 'casino_preferences', 'casino_games', 'casino_ledger')
        backup = {}
        async with original(read_only=True) as conn:
            async with conn.cursor() as cursor:
                for table in tables:
                    chunks = []
                    async with cursor.copy(sql.SQL('COPY {} TO STDOUT (FORMAT BINARY)').format(sql.Identifier(self.schema, table))) as stream:
                        async for block in stream:
                            chunks.append(bytes(block))
                    backup[table] = b''.join(chunks)
        restored_schema = 'casino_test_' + uuid.uuid4().hex
        restored_crystals = CrystalStore(read_database_url(), schema=restored_schema)
        self.addAsyncCleanup(restored_crystals.close)
        async with original() as conn:
            await conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(restored_schema)))

        async def cleanup():
            if not re.fullmatch(r'casino_test_[0-9a-f]{32}', restored_schema):
                raise AssertionError('Invalid restore test schema')
            async with original() as conn:
                await conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(restored_schema)))
        self.addAsyncCleanup(cleanup)
        await restored_crystals.initialize()
        restored = CasinoStore(restored_crystals)
        await restored.initialize()
        async with restored_crystals.connection() as conn:
            async with conn.cursor() as cursor:
                for table in tables:
                    async with cursor.copy(sql.SQL('COPY {} FROM STDIN (FORMAT BINARY)').format(sql.Identifier(restored_schema, table))) as stream:
                        await stream.write(backup[table])
                await cursor.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s, 'id'), (SELECT max(id) FROM {}))").format(sql.Identifier(restored_schema, 'casino_ledger')),
                                     (restored_schema + '.casino_ledger',))
        game = await restored.recover(123)
        self.assertEqual((game.status, game.net), ('settled', 10))
        self.assertEqual(await restored.balance(123), 1010)
        self.assertEqual(len(await restored.ledger(123, game.id)), 2)
        self.assertEqual(await self.casino.balance(123), 990)


    async def test_reopening_lobby_invalidates_old_settings_without_debit(self):
        from casino_commands import CasinoFeature
        from test_casino_ui import interaction
        prefs = await self.casino.settings(123)
        feature = CasinoFeature(self.casino)
        feature.dealer_path = 'missing-placeholder'
        await feature.slash(interaction())
        with self.assertRaises(CasinoError):
            await self.casino.start(123, prefs.token)
        self.assertEqual(await self.casino.balance(123), 1000)

if __name__ == "__main__":
    unittest.main()
