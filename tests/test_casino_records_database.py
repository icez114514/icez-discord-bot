"""Read contracts backed by real casino settlements in disposable schemas."""

import os
import unittest

import test_casino_database as fixtures
from casino_store import CasinoStore


@unittest.skipUnless(os.getenv('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for isolated PostgreSQL tests')
class RecordsDatabaseTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = fixtures.CasinoDatabaseTests.__dict__['setUpClass']
    asyncSetUp = fixtures.CasinoDatabaseTests.asyncSetUp
    drop_schema = fixtures.CasinoDatabaseTests.drop_schema

    async def test_settled_history_and_house_rebuild_from_real_ledger(self):
        from casino_records import CasinoRecords
        prefs = await self.casino.settings(123)
        prefs = await self.casino.choose(123, prefs.token, base=100)
        game = await self.casino.start(123, prefs.token)
        await self.casino.leave(123, game_id=game.id)
        records = CasinoRecords(CasinoStore(self.crystals))
        summary = await records.summary(user_id=123)
        settled = summary.rows[0]
        self.assertEqual((settled.game, settled.status, settled.count, settled.wins,
                          settled.losses, settled.ties, settled.wager, settled.returned, settled.net),
                         ('dice', 'settled', 1, 1, 0, 0, 100, 200, 100))
        house = (await records.summary()).rows[0]
        self.assertEqual((house.wager, house.returned, -house.net), (100, 200, -100))
        history = await records.history(user_id=123)
        record = history.rows[0]
        self.assertEqual((record.id, record.original_wager, record.wager, record.returned, record.net),
                         (game.id, 100, 100, 200, 100))
        self.assertEqual([entry.kind for entry in record.entries], ['stake', 'payout'])
        self.assertEqual(sum(entry.amount for entry in record.entries), 100)
        self.assertEqual((await records.history(user_id=456, game_id=game.id)).rows, ())
        self.assertEqual((await records.history(user_id=123, game='blackjack')).rows, ())

    async def test_mixed_games_double_refund_and_active_are_separate_and_paginated(self):
        from casino_records import CasinoRecords
        from test_blackjack_database import deck
        from psycopg import sql
        for dice in ((6, 6, 6, 1, 2, 3), (1, 2, 3, 6, 6, 6), (6, 6, 6, 6, 6, 6)):
            casino = CasinoStore(self.crystals, roll=lambda: dice)
            pref = await casino.settings(123)
            game = await casino.start(123, pref.token)
            await casino.leave(123, game_id=game.id)
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12))
        pref = await casino.settings(123)
        game = await casino.start(123, pref.token, game='blackjack')
        game = await casino.play(123, game.id, game.version, 'double')
        self.assertEqual((game.wager, game.returned), (20, 40))
        await casino.leave(123, game_id=game.id)
        natural = CasinoStore(self.crystals, deck=lambda: deck(0, 8, 12, 20))
        pref = await natural.settings(123)
        game = await natural.start(123, pref.token, game='blackjack')
        self.assertEqual(game.returned, 25)
        await natural.leave(123, game_id=game.id)
        pref = await casino.settings(123)
        broken = await casino.start(123, pref.token, game='blackjack')
        async with self.crystals.connection() as conn:
            await conn.execute(sql.SQL("UPDATE {} SET cards='{{}}'::jsonb WHERE id=%s").format(
                sql.Identifier(self.schema, 'casino_games')), (broken.id,))
        void = await casino.recover(123)
        self.assertEqual(void.status, 'void')
        await casino.leave(123, game_id=void.id)
        pref = await casino.settings(123)
        active = await casino.start(123, pref.token, game='blackjack')
        records = CasinoRecords(CasinoStore(self.crystals))
        first = await records.summary(user_id=123)
        self.assertTrue(first.has_next)
        second = await records.summary(user_id=123, page=1)
        self.assertFalse(second.has_next)
        totals = {(r.game, r.status): (r.count, r.wins, r.losses, r.ties, r.wager, r.returned, r.net)
                  for r in first.rows + second.rows}
        self.assertEqual(totals, {
            ('dice', 'settled'): (3, 1, 1, 1, 30, 30, 0),
            ('blackjack', 'settled'): (2, 2, 0, 0, 30, 65, 35),
            ('blackjack', 'void'): (1, 0, 0, 0, 10, 10, 0),
            ('blackjack', 'active'): (1, 0, 0, 0, 10, 0, -10),
        })
        ids = []
        for number in range(7):
            page = await records.history(user_id=123, page=number)
            row = page.rows[0]
            ids.append(row.id)
            self.assertEqual(page.has_next, number < 6)
            self.assertEqual(sum(e.amount for e in row.entries), row.net)
            for entry in row.entries:
                self.assertEqual(entry.after, entry.before + entry.amount)
        self.assertEqual(len(set(ids)), 7)
        self.assertEqual(ids[0], active.id)
        self.assertEqual((await records.history(user_id=123, page=7)).rows, ())
        for game_id in (active.id, void.id):
            row = (await records.history(user_id=None, game_id=game_id)).rows[0]
            self.assertFalse(hasattr(row, 'cards'))
            self.assertFalse(hasattr(row, 'dealer'))
            self.assertFalse(hasattr(row, 'dice'))
        house = (await records.summary()).rows + (await records.summary(page=1)).rows
        self.assertEqual(sum(-r.net for r in house), -25)
        filtered = await records.summary(user_id=123, game='dice')
        self.assertEqual(len(filtered.rows), 1)
        self.assertEqual(filtered.rows[0].count, 3)
        # Future persisted game identifiers use the same ledger/query contract.
        async with self.crystals.connection() as conn:
            await conn.execute(sql.SQL("UPDATE {} SET game='future' WHERE game='dice'").format(
                sql.Identifier(self.schema, 'casino_games')))
        self.assertEqual((await records.summary(game='future')).rows[0].count, 3)

    async def test_real_records_reach_private_audit_and_public_house_without_cards(self):
        import os
        from unittest.mock import patch
        from casino_records import CasinoRecords
        from casino_commands import CasinoFeature, LobbyView, AuditView, AuditModal
        from test_casino_ui import interaction
        from test_blackjack_database import deck
        casino = CasinoStore(self.crystals, deck=lambda: deck(4, 8, 5, 20, 12))
        pref = await casino.settings(123)
        active = await casino.start(123, pref.token, game='blackjack')
        feature = CasinoFeature(casino)
        event = interaction()
        await feature.act(event, LobbyView(feature, 123), 'records')
        summary_view = event.followup.send.call_args.kwargs['view']
        detail = interaction()
        await feature.act(detail, summary_view, 'toggle')
        payload = detail.edit_original_response.call_args.kwargs
        rendered = str(payload['embed'].to_dict())
        self.assertIn(str(active.id), rendered)
        self.assertIn('stake', rendered)
        for private in ('cards', 'dealer', 'deck', 'player', '[4, 5]', '[8, 20]'):
            self.assertNotIn(private, rendered)
        with patch.dict(os.environ, {'CASINO_AUDITOR_IDS': '456'}):
            modal = AuditModal(AuditView(feature, 456), 'audit_game')
            modal.value._value = str(active.id)
            admin = interaction(456)
            await modal.on_submit(admin)
            self.assertTrue(admin.followup.send.call_args.kwargs['ephemeral'])
            self.assertIn(str(active.id), str(admin.followup.send.call_args.kwargs['embed'].to_dict()))
        public = interaction()
        await feature.act(public, LobbyView(feature, 123), 'house')
        result = public.followup.send.call_args.kwargs
        self.assertFalse(result['ephemeral'])
        self.assertNotIn(str(active.id), str(result['embed'].to_dict()))
        self.assertNotIn('123', str(result['embed'].to_dict()))
        self.assertEqual((await CasinoRecords(casino).history(user_id=456, game_id=active.id)).rows, ())
