"""Pai Gow accepted behavior through durable casino operations."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
import unittest

import test_casino_database as fixtures
from casino_store import CasinoStore
from casino_rules import CasinoError
from casino_records import CasinoRecords


@unittest.skipUnless(os.getenv('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for isolated PostgreSQL tests')
class PaiGowDatabaseTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = fixtures.CasinoDatabaseTests.__dict__['setUpClass']
    asyncSetUp = fixtures.CasinoDatabaseTests.asyncSetUp
    drop_schema = fixtures.CasinoDatabaseTests.drop_schema

    async def test_select_recover_confirm_replay_and_records(self):
        now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)), clock=lambda: now)
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='paigow')
        self.assertEqual((game.status, game.dealer, game.front), ('active', (None,) * 7, ()))
        self.assertEqual(game.deadline, now + timedelta(seconds=120))
        self.assertEqual(await casino.balance(123), 990)
        with self.assertRaises(CasinoError):
            await casino.play_paigow(123, game.id, game.version, 'confirm')
        with self.assertRaises(CasinoError):
            await casino.play_paigow(456, game.id, game.version, 'auto')
        selected = await casino.play_paigow(123, game.id, game.version, 'auto')
        self.assertEqual(selected.deadline, game.deadline)
        self.assertEqual(len(selected.front), 2)
        self.assertEqual(selected.dealer_front, ())
        restored = await CasinoStore(self.crystals, clock=lambda: now).recover(123)
        self.assertEqual(restored, selected)
        self.assertEqual(await casino.play_paigow(123, game.id, game.version, 'confirm'), selected)
        result = await casino.play_paigow(123, game.id, selected.version, 'confirm')
        self.assertEqual(result.status, 'settled')
        self.assertNotIn(None, result.dealer)
        self.assertEqual(len(result.dealer_front), 2)
        self.assertEqual(result.returned, {'win': 20, 'tie': 10, 'loss': 0}[result.outcome])
        self.assertEqual(sum(e.amount for e in await casino.ledger(123, game.id)), result.net)
        records = await CasinoRecords(casino).history(user_id=123, game='paigow')
        self.assertEqual(records.rows[0].id, game.id)
        child, duplicate = await asyncio.gather(casino.replay(123, game.id), casino.replay(123, game.id))
        self.assertEqual(child.id, duplicate.id)
        self.assertEqual(child.game, 'paigow')
        self.assertEqual(len(await casino.ledger(123, child.id)), 1)

    async def test_expiry_versus_confirm_only_returns_once(self):
        now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)), clock=lambda: now)
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='paigow')
        selected = await casino.play_paigow(123, game.id, game.version, 'auto')
        now = game.deadline
        await asyncio.gather(casino.expire_pending(),
                             casino.play_paigow(123, game.id, selected.version, 'confirm'))
        result = await casino.recover(123)
        self.assertEqual(result.status, 'settled')
        self.assertEqual(len(await casino.ledger(123, game.id)), 2)
        self.assertEqual(await casino.expire_pending(), [])

    async def test_invalid_selection_cross_game_guard_and_unchanged_deadline(self):
        now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)), clock=lambda: now)
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='paigow')
        now += timedelta(seconds=90)
        for selection in ([0, 0], [0, 1], [], [0, 2, 4]):
            with self.assertRaises(CasinoError):
                await casino.play_paigow(123, game.id, game.version, 'select', selection)
        self.assertEqual(await casino.recover(123), game)
        with self.assertRaises(CasinoError):
            await casino.start(123, __import__('uuid').uuid4(), game='blackjack')
        chosen = await casino.play_paigow(123, game.id, game.version, 'select', [8, 10])
        self.assertEqual(chosen.front, (8, 10))
        self.assertEqual(chosen.deadline, game.deadline)
        self.assertEqual(len(await casino.ledger(123, game.id)), 1)
        await casino.initialize()
        await casino.initialize()
        self.assertEqual(await casino.recover(123), chosen)
        now = game.deadline
        expired = await casino.recover(123)
        self.assertEqual(expired.status, 'settled')

    async def test_corrupt_persisted_state_refunds_once_without_revealing_cards(self):
        from psycopg.types.json import Jsonb
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)))
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='paigow')
        # Fault injection at the persistence boundary: simulate an unrecoverable stored payload.
        async with self.crystals.connection() as conn:
            await casino.execute(conn, 'UPDATE {games} SET cards=%s WHERE id=%s',
                                 (Jsonb({'player': [52], 'rules': 'broken'}), game.id))
        recovered = await casino.recover(123)
        self.assertEqual((recovered.status, recovered.returned, recovered.net), ('void', 10, 0))
        self.assertEqual((recovered.player, recovered.dealer, recovered.front), ((), (), ()))
        self.assertEqual(await casino.recover(123), recovered)
        self.assertEqual([(e.kind, e.amount) for e in await casino.ledger(123, game.id)],
                         [('stake', -10), ('refund', 10)])

    async def test_confirmation_commit_faults_never_double_return(self):
        from contextlib import asynccontextmanager
        from database import DatabaseError
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)))
        for phase in ('before', 'after'):
            prefs = await casino.settings(123)
            game = await casino.start(123, prefs.token, game='paigow')
            selected = await casino.play_paigow(123, game.id, game.version, 'auto')
            original = self.crystals.connection
            calls = 0
            @asynccontextmanager
            async def fault(**kwargs):
                nonlocal calls
                calls += 1
                inject = calls == 1
                async with original(**kwargs) as conn:
                    yield conn
                    if inject and phase == 'before':
                        raise DatabaseError('Injected pre-commit failure')
                if inject and phase == 'after':
                    raise DatabaseError('Injected lost commit acknowledgement')
            self.crystals.connection = fault
            try:
                if phase == 'before':
                    with self.assertRaises(DatabaseError):
                        await casino.play_paigow(123, game.id, selected.version, 'confirm')
                else:
                    self.assertEqual((await casino.play_paigow(
                        123, game.id, selected.version, 'confirm')).status, 'settled')
            finally:
                self.crystals.connection = original
            if phase == 'before':
                self.assertEqual(await casino.recover(123), selected)
                self.assertEqual(len(await casino.ledger(123, game.id)), 1)
            result = await casino.play_paigow(123, game.id, selected.version, 'confirm')
            self.assertEqual(result.status, 'settled')
            self.assertEqual(len(await casino.ledger(123, game.id)), 2)
            self.assertEqual(sum(e.amount for e in await casino.ledger(123, game.id)), result.net)
            await casino.leave(123, game_id=game.id)

    async def test_large_wager_and_start_commit_acknowledgement_recover_once(self):
        from contextlib import asynccontextmanager
        from database import Account, DatabaseError
        amount = 10 ** 100
        await self.crystals.import_accounts([Account(987, amount * 3)], dry_run=False)
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)))
        prefs = await casino.settings(987)
        prefs = await casino.choose(987, prefs.token, base=amount)
        original = self.crystals.connection
        calls = 0
        @asynccontextmanager
        async def fault(**kwargs):
            nonlocal calls
            calls += 1
            inject = calls == 1
            async with original(**kwargs) as conn:
                yield conn
            if inject:
                raise DatabaseError('Injected lost opening commit acknowledgement')
        self.crystals.connection = fault
        try:
            game = await casino.start(987, prefs.token, game='paigow')
        finally:
            self.crystals.connection = original
        duplicate = await casino.start(987, prefs.token, game='paigow')
        self.assertEqual(game, duplicate)
        self.assertEqual(await casino.balance(987), amount * 2)
        selected = await casino.play_paigow(987, game.id, game.version, 'auto')
        result = await casino.play_paigow(987, game.id, selected.version, 'confirm')
        self.assertEqual(result.returned, amount * {'win': 2, 'tie': 1, 'loss': 0}[result.outcome])
        self.assertEqual(sum(e.amount for e in await casino.ledger(987, game.id)), result.net)

    async def test_discord_full_flow_and_image_failure_do_not_repeat_money(self):
        from unittest.mock import AsyncMock, patch
        from casino_commands import CasinoFeature, LobbyView, PaiGowView, ResultView, SettingsView
        from test_casino_ui import interaction
        casino = CasinoStore(self.crystals, pai_deck=lambda: list(range(53)))
        feature, event = CasinoFeature(casino), interaction()
        with patch.object(feature, 'table_image', new=AsyncMock(side_effect=OSError('injected image failure'))):
            await feature.act(event, LobbyView(feature, 123), 'paigow')
            settings = event.edit_original_response.call_args.kwargs['view']
            self.assertIsInstance(settings, SettingsView)
            self.assertEqual(settings.game_type, 'paigow')
            await feature.act(event, settings, 'start')
            playing = event.edit_original_response.call_args.kwargs['view']
            self.assertIsInstance(playing, PaiGowView)
            await feature.act(event, playing, 'pai_select', ['8', '10'])
            selected = event.edit_original_response.call_args.kwargs['view']
            self.assertEqual(selected.game.front, (8, 10))
            await feature.slash(event)
            self.assertEqual(event.edit_original_response.call_args.kwargs['view'].game, selected.game)
            await feature.act(event, selected, 'pai_confirm')
            result = event.edit_original_response.call_args.kwargs['view']
            self.assertIsInstance(result, ResultView)
            self.assertEqual(len(await casino.ledger(123, result.game.id)), 2)
            await feature.act(event, result, 'settings')
            settings = event.edit_original_response.call_args.kwargs['view']
            self.assertEqual(settings.game_type, 'paigow')
