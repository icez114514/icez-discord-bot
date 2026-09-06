"""Blackjack acceptance through durable operations in an isolated schema."""

from datetime import datetime, timedelta, timezone
import os
import unittest
import asyncio

import test_casino_database as fixtures
from casino_store import CasinoStore


def deck(*prefix):
    return list(prefix) + [card for card in range(52) if card not in prefix]


@unittest.skipUnless(os.getenv('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for isolated PostgreSQL tests')
class BlackjackDatabaseTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = fixtures.CasinoDatabaseTests.__dict__['setUpClass']
    asyncSetUp = fixtures.CasinoDatabaseTests.asyncSetUp
    drop_schema = fixtures.CasinoDatabaseTests.drop_schema

    async def test_fixed_cards_cover_naturals_bust_soft_aces_and_dealer_draws(self):
        cases = [
            ((8, 0, 20, 12), None, 'loss', 0, (8, 20)),
            ((0, 13, 12, 25), None, 'tie', 10, (0, 12)),
            ((9, 8, 7, 20, 5), 'hit', 'loss', 0, (9, 7, 5)),
            ((4, 8, 5, 20, 9), 'hit', 'win', 20, (4, 5, 9)),
            ((0, 8, 5, 20, 9), 'hit-stand', 'tie', 10, (0, 5, 9)),
            ((0, 8, 13, 20), 'stand', 'loss', 0, (0, 13)),
            ((9, 2, 8, 3, 12), 'stand', 'win', 20, (9, 8)),
            ((9, 8, 7, 5, 12), 'stand', 'win', 20, (9, 7)),
        ]
        for cards, action, outcome, returned, player in cases:
            with self.subTest(cards=cards):
                casino = CasinoStore(self.crystals, deck=lambda: deck(*cards))
                prefs = await casino.settings(123)
                game = await casino.start(123, prefs.token, game='blackjack')
                if action:
                    for step in action.split('-'):
                        game = await casino.play(123, game.id, game.version, step)
                self.assertEqual((game.status, game.outcome, game.returned, game.player),
                                 ('settled', outcome, returned, player))
                await casino.leave(123, game_id=game.id)

    async def test_insufficient_double_and_invalid_action_preserve_original_turn(self):
        from casino_rules import CasinoError
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20))
        prefs = await casino.settings(123)
        prefs = await casino.choose(123, prefs.token, base=1000)
        game = await casino.start(123, prefs.token, game='blackjack')
        for action in ('double', 'split', 'insurance'):
            with self.assertRaises(CasinoError):
                await casino.play(123, game.id, game.version, action)
        with self.assertRaises(CasinoError):
            await casino.play(456, game.id, game.version, 'stand')
        self.assertEqual(await casino.recover(123), game)
        self.assertEqual(await casino.balance(123), 0)
        self.assertEqual(len(await casino.ledger(123, game.id)), 1)

    async def test_double_commit_faults_rollback_or_recover_without_second_debit(self):
        from contextlib import asynccontextmanager
        from database import DatabaseError
        for phase in ('before', 'after', 'crash'):
            with self.subTest(phase=phase):
                casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12))
                prefs = await casino.settings(123)
                game = await casino.start(123, prefs.token, game='blackjack')
                original = self.crystals.connection
                count = 0
                @asynccontextmanager
                async def fault(**kwargs):
                    nonlocal count
                    count += 1
                    inject = count == 1
                    async with original(**kwargs) as conn:
                        yield conn
                        if inject and phase == 'before':
                            raise DatabaseError('Injected pre-COMMIT failure')
                    if inject:
                        if phase == 'crash':
                            raise SystemExit('Injected process death')
                        if phase == 'after':
                            raise DatabaseError('Injected lost acknowledgement')
                self.crystals.connection = fault
                try:
                    try:
                        await casino.play(123, game.id, game.version, 'double')
                    except (DatabaseError, SystemExit):
                        pass
                finally:
                    self.crystals.connection = original
                restored = await CasinoStore(self.crystals).recover(123)
                if phase == 'before':
                    self.assertEqual(restored, game)
                    self.assertEqual(len(await casino.ledger(123, game.id)), 1)
                result = await casino.play(123, game.id, game.version, 'double')
                self.assertEqual((result.wager, result.returned), (20, 40))
                entries = await casino.ledger(123, game.id)
                self.assertEqual([(e.kind, e.amount) for e in entries], [('stake', -10), ('double', -10), ('payout', 40)])
                self.assertEqual(sum(e.amount for e in entries), result.net)
                await casino.leave(123, game_id=game.id)

    async def test_unrecoverable_doubled_state_refunds_all_principal_once(self):
        from unittest.mock import patch
        import blackjack
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12))
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='blackjack')
        original = blackjack.act
        def corrupt(state, action):
            original(state, action)
            state['deck'] = []
        with patch('blackjack.act', side_effect=corrupt):
            result = await casino.play(123, game.id, game.version, 'double')
        self.assertEqual((result.status, result.wager, result.returned, result.net), ('void', 20, 20, 0))
        self.assertEqual(await casino.balance(123), 1000)
        self.assertEqual(await casino.recover(123), result)
        self.assertEqual([(e.kind, e.amount) for e in await casino.ledger(123, game.id)],
                         [('stake', -10), ('double', -10), ('refund', 20)])

    async def test_expiry_sweep_and_player_race_settle_once_after_restart(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, deck=lambda: deck(9, 8, 7, 20), clock=lambda: now)
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='blackjack')
        now = game.deadline
        restarted = CasinoStore(self.crystals, clock=lambda: now)
        await asyncio.gather(restarted.expire_pending(), casino.play(123, game.id, game.version, 'double'))
        result = await restarted.recover(123)
        self.assertEqual((result.wager, result.returned), (10, 20))
        self.assertEqual(len(await casino.ledger(123, game.id)), 2)
        self.assertEqual(await restarted.expire_pending(), [])

    async def test_v1_upgrade_preserves_dice_history_and_repeated_upgrade_keeps_deadline(self):
        from psycopg import sql
        prefs = await self.casino.settings(123)
        dice = await self.casino.start(123, prefs.token)
        history = await self.casino.ledger(123, dice.id)
        async with self.crystals.connection() as conn:
            games = sql.Identifier(self.schema, 'casino_games')
            ledger = sql.Identifier(self.schema, 'casino_ledger')
            await conn.execute(sql.SQL('ALTER TABLE {} DROP COLUMN cards, DROP COLUMN deadline, DROP CONSTRAINT casino_wager_valid').format(games))
            await conn.execute(sql.SQL('ALTER TABLE {} ADD CHECK (wager = base * multiplier)').format(games))
            await conn.execute(sql.SQL('ALTER TABLE {} DROP CONSTRAINT casino_ledger_kind_check').format(ledger))
            await conn.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT casino_ledger_kind_check CHECK (kind IN ('stake','payout','refund'))").format(ledger))
        from database import DatabaseError
        with self.assertRaises(DatabaseError):
            await self.casino.check()
        await self.casino.initialize()
        self.assertEqual(await self.casino.recover(123), dice)
        self.assertEqual(await self.casino.ledger(123, dice.id), history)
        await self.casino.leave(123, game_id=dice.id)
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12))
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='blackjack')
        await casino.initialize()
        await casino.initialize()
        self.assertEqual(await casino.recover(123), game)
        result = await casino.play(123, game.id, game.version, 'double')
        self.assertEqual((result.wager, result.returned), (20, 40))

    async def test_binary_backup_restores_original_deck_deadline_and_money(self):
        import re
        import uuid
        from psycopg import sql
        from database import CrystalStore, read_database_url
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12), clock=lambda: now)
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='blackjack')
        tables = ('crystal_accounts', 'casino_preferences', 'casino_games', 'casino_ledger')
        backup = {}
        async with self.crystals.connection(read_only=True) as conn:
            async with conn.cursor() as cursor:
                for table in tables:
                    chunks = []
                    async with cursor.copy(sql.SQL('COPY {} TO STDOUT (FORMAT BINARY)').format(sql.Identifier(self.schema, table))) as stream:
                        async for block in stream:
                            chunks.append(bytes(block))
                    backup[table] = b''.join(chunks)
        schema = 'casino_test_' + uuid.uuid4().hex
        crystals = CrystalStore(read_database_url(), schema=schema)
        self.addAsyncCleanup(crystals.close)
        async with crystals.connection() as conn:
            await conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        async def cleanup():
            self.assertRegex(schema, r'^casino_test_[0-9a-f]{32}$')
            async with crystals.connection() as conn:
                await conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        self.addAsyncCleanup(cleanup)
        await crystals.initialize()
        restored = CasinoStore(crystals, clock=lambda: now)
        await restored.initialize()
        async with crystals.connection() as conn:
            async with conn.cursor() as cursor:
                for table in tables:
                    async with cursor.copy(sql.SQL('COPY {} FROM STDIN (FORMAT BINARY)').format(sql.Identifier(schema, table))) as stream:
                        await stream.write(backup[table])
                await cursor.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'id'),(SELECT max(id) FROM {}))").format(sql.Identifier(schema, 'casino_ledger')), (schema + '.casino_ledger',))
        self.assertEqual(await restored.recover(123), game)
        result = await restored.play(123, game.id, game.version, 'double')
        self.assertEqual((result.wager, result.returned), (20, 40))
        self.assertEqual(await restored.balance(123), 1020)
        self.assertEqual(await casino.balance(123), 990)
        self.assertEqual(len(await restored.ledger(123, game.id)), 3)

    async def test_image_failure_recovery_and_reopen_preserve_money(self):
        from casino_commands import CasinoFeature, LobbyView, SettingsView, PlayView, ResultView
        from test_casino_ui import interaction
        from unittest.mock import patch, AsyncMock
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12))
        feature = CasinoFeature(casino)
        event = interaction()
        with patch.object(feature, 'table_image', new=AsyncMock(side_effect=OSError('injected composition failure'))):
            await feature.act(event, LobbyView(feature, 123), 'blackjack')
            settings = event.edit_original_response.call_args.kwargs['view']
            self.assertIsInstance(settings, SettingsView)
            self.assertEqual(settings.game_type, 'blackjack')
            await feature.act(event, settings, 'start')
            playing = event.edit_original_response.call_args.kwargs['view']
            self.assertIsInstance(playing, PlayView)
            before = await casino.balance(123)
            await feature.slash(event)
            recovered = event.edit_original_response.call_args.kwargs['view']
            self.assertEqual(recovered.game, playing.game)
            self.assertEqual(await casino.balance(123), before)
        await feature.slash(event)
        self.assertTrue(event.edit_original_response.call_args.kwargs['attachments'])
        self.assertEqual(await casino.balance(123), before)
        await feature.act(event, recovered, 'double')
        result = event.edit_original_response.call_args.kwargs['view']
        self.assertIsInstance(result, ResultView)
        self.assertEqual(result.game.returned, 40)
        await feature.act(event, result, 'replay')
        child = event.edit_original_response.call_args.kwargs['view'].game
        self.assertEqual((child.bet.total, child.wager), (10, 10))
        await feature.act(event, result, 'replay')
        self.assertEqual(event.edit_original_response.call_args.kwargs['view'].game.id, child.id)
        self.assertEqual(await casino.balance(123), 1010)
        self.assertEqual(len(await casino.ledger(123, child.id)), 1)

    async def test_double_is_atomic_once_and_replay_uses_original_bet(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12), clock=lambda: now)
        prefs = await casino.settings(123)
        prefs = await casino.choose(123, prefs.token, base=100, multiplier=2)
        game = await casino.start(123, prefs.token, game='blackjack')
        self.assertEqual((game.status, game.player, game.dealer), ('active', (4, 5), (8, None)))
        self.assertEqual(game.deadline, now + timedelta(seconds=120))
        other = CasinoStore(self.crystals, clock=lambda: now)
        results = await asyncio.gather(casino.play(123, game.id, game.version, 'double'),
                                       other.play(123, game.id, game.version, 'double'))
        self.assertEqual(results[0], results[1])
        result = results[0]
        self.assertEqual((result.status, result.wager, result.returned), ('settled', 400, 800))
        self.assertEqual(result.player, (4, 5, 12))
        self.assertEqual([(e.kind, e.amount) for e in await casino.ledger(123, game.id)],
                         [('stake', -200), ('double', -200), ('payout', 800)])
        child = await casino.replay(123, game.id)
        self.assertEqual((child.game, child.bet.base, child.bet.multiplier, child.wager),
                         ('blackjack', 100, 2, 200))

    async def test_hit_refreshes_only_valid_turn_and_expiry_stands_after_restart(self):
        from casino_rules import CasinoError
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, deck=lambda: deck(0, 13, 4, 18, 2, 9), clock=lambda: now)
        prefs = await casino.settings(123)
        game = await casino.start(123, prefs.token, game='blackjack')
        now += timedelta(seconds=100)
        restarted = CasinoStore(self.crystals, clock=lambda: now)
        self.assertEqual((await restarted.recover(123)).deadline, game.deadline)
        with self.assertRaises(CasinoError):
            await casino.settings(123)
        with self.assertRaises(CasinoError):
            await casino.leave(123)
        hit = await casino.play(123, game.id, game.version, 'hit')
        self.assertEqual(hit.player, (0, 4, 2))
        self.assertEqual(hit.deadline, now + timedelta(seconds=120))
        now += timedelta(seconds=50)
        duplicate = await restarted.play(123, game.id, game.version, 'hit')
        self.assertEqual(duplicate, hit)
        with self.assertRaises(CasinoError):
            await casino.play(123, game.id, hit.version, 'double')
        self.assertEqual((await restarted.recover(123)).deadline, hit.deadline)
        now = hit.deadline
        result = await restarted.play(123, game.id, hit.version, 'hit')
        self.assertEqual((result.player, result.dealer, result.outcome), ((0, 4, 2), (13, 18), 'win'))
        self.assertEqual((result.status, result.returned), ('settled', 20))
        self.assertEqual(len(await casino.ledger(123, game.id)), 2)

    async def test_natural_pays_exactly_and_recovery_never_deals_again(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        casino = CasinoStore(self.crystals, deck=lambda: deck(0, 8, 12, 20), clock=lambda: now)
        prefs = await casino.settings(123)
        prefs = await casino.choose(123, prefs.token, base=100)
        game = await casino.start(123, prefs.token, game='blackjack')
        self.assertEqual((game.status, game.outcome, game.returned), ('settled', 'win', 250))
        self.assertEqual(await casino.balance(123), 1150)
        restored = await CasinoStore(self.crystals).recover(123)
        self.assertEqual(restored, game)
        self.assertEqual([(e.kind, e.amount) for e in await casino.ledger(123, game.id)],
                         [('stake', -100), ('payout', 250)])
