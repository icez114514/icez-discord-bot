from casino_store import LobbySnapshot
"""Private query delivery and authorization at Discord interaction boundaries."""

import unittest
from unittest.mock import AsyncMock, patch

from casino_commands import CasinoFeature, LobbyView
from casino_records import Page, Summary
from test_casino_ui import interaction


class RecordsUITests(unittest.IsolatedAsyncioTestCase):
    async def test_private_history_is_separate_and_scoped_to_clicker(self):
        feature = CasinoFeature(None)
        event = interaction()
        with patch('casino_commands.CasinoRecords') as queries:
            queries.return_value.summary = AsyncMock(return_value=Page((
                Summary('dice', 'settled', 1, 1, 0, 0, 100, 200),), False))
            feature.store = object()
            await feature.act(event, LobbyView(feature, 123), 'records')
        self.assertFalse(event.edit_original_response.called)
        self.assertTrue(event.response.defer.call_args.kwargs['ephemeral'])
        result = event.followup.send.call_args.kwargs
        self.assertTrue(result['ephemeral'])
        self.assertIn('完成', str(result['embed'].to_dict()))
        self.assertEqual(result['view'].user_id, 123)

    async def test_pages_filter_and_old_or_foreign_buttons_cannot_read_details(self):
        from casino_commands import RecordsView
        feature = CasinoFeature(None)
        feature.store = object()
        original = RecordsView(feature, 123, has_next=True)
        with patch('casino_commands.CasinoRecords') as queries:
            queries.return_value.summary = AsyncMock(return_value=Page((), False))
            queries.return_value.history = AsyncMock(return_value=Page((), False))
            event = interaction()
            await feature.act(event, original, 'next')
            page = event.edit_original_response.call_args.kwargs['view']
            self.assertEqual(page.page, 1)
            stranger = interaction(456)
            await feature.act(stranger, page, 'toggle')
            self.assertFalse(stranger.edit_original_response.called)
            self.assertFalse(stranger.followup.send.called)
            stale = interaction()
            await feature.act(stale, original, 'toggle')
            self.assertFalse(stale.edit_original_response.called)
            self.assertFalse(stale.followup.send.called)
            event = interaction()
            await feature.act(event, page, 'filter')
            modal = event.response.send_modal.call_args.args[0]
            modal.value._value = 'blackjack'
            submitted = interaction()
            await modal.on_submit(submitted)
            filtered = submitted.edit_original_response.call_args.kwargs['view']
            self.assertEqual((filtered.game_filter, filtered.page, filtered.user_id), ('blackjack', 0, 123))
            event = interaction()
            await feature.act(event, filtered, 'toggle')
            self.assertTrue(event.edit_original_response.call_args.kwargs['view'].detail)
            self.assertEqual(queries.return_value.history.call_args.kwargs['user_id'], 123)

    async def test_audit_entry_modal_and_pages_recheck_live_permissions(self):
        import os
        from casino_commands import AuditView
        feature = CasinoFeature(None)
        feature.store = AsyncMock()
        feature.store.balance.return_value = None
        feature.render = AsyncMock()
        with patch.dict(os.environ, {'CASINO_AUDITOR_IDS': '123'}):
            event = interaction()
            await feature.show_lobby(event, LobbySnapshot(None))
            entry = event.followup.send.call_args.kwargs
            self.assertTrue(entry['ephemeral'])
            self.assertIsInstance(entry['view'], AuditView)
            event = interaction()
            await feature.act(event, entry['view'], 'audit_player')
            modal = event.response.send_modal.call_args.args[0]
            modal.value._value = '456'
            with patch('casino_commands.CasinoRecords') as queries:
                queries.return_value.history = AsyncMock(return_value=Page((), True))
                submitted = interaction()
                await modal.on_submit(submitted)
                result = submitted.followup.send.call_args.kwargs
                self.assertTrue(result['ephemeral'])
                self.assertEqual((result['view'].user_id, result['view'].audit), (456, True))
                os.environ['CASINO_AUDITOR_IDS'] = ''
                revoked = interaction()
                await feature.act(revoked, result['view'], 'next')
                self.assertFalse(revoked.edit_original_response.called)
                self.assertTrue(revoked.response.defer.called)
                self.assertTrue(revoked.followup.send.call_args.kwargs['ephemeral'])
                self.assertNotIn('embed', revoked.followup.send.call_args.kwargs)
                revoked_modal = interaction()
                await modal.on_submit(revoked_modal)
                self.assertTrue(revoked_modal.response.defer.called)
                self.assertNotIn('embed', revoked_modal.followup.send.call_args.kwargs)
            ordinary = interaction()
            ordinary.user.guild_permissions = type('Permissions', (), {'administrator': True})()
            await feature.show_lobby(ordinary, LobbySnapshot(None))
            self.assertFalse(ordinary.followup.send.called)

    async def test_owner_is_authorized_but_other_app_team_members_are_not(self):
        from types import SimpleNamespace
        feature = CasinoFeature(None)
        event = interaction()
        event.client = SimpleNamespace(application_info=AsyncMock(return_value=SimpleNamespace(
            owner=SimpleNamespace(id=123), team=None)))
        self.assertTrue(await feature.is_auditor(event))
        event.client.application_info.return_value = SimpleNamespace(
            owner=SimpleNamespace(id=999), team=SimpleNamespace(owner_id=456))
        self.assertFalse(await feature.is_auditor(event))

    async def test_house_wins_are_inverse_of_player_wins_and_do_not_expose_identity(self):
        feature = CasinoFeature(None)
        feature.store = object()
        with patch('casino_commands.CasinoRecords') as queries:
            queries.return_value.summary = AsyncMock(return_value=Page((
                Summary('dice', 'settled', 1, 1, 0, 0, 100, 200),), False))
            event = interaction()
            await feature.act(event, LobbyView(feature, 123), 'house')
            payload = event.followup.send.call_args.kwargs
            self.assertFalse(payload['ephemeral'])
            rendered = str(payload['embed'].to_dict())
            self.assertIn('勝 0／負 1／平 0', rendered)
            self.assertIn('淨額 -100', rendered)
            self.assertNotIn('123', rendered)

    async def test_foreign_admin_guessed_ids_invalid_input_and_mid_query_revocation(self):
        import os
        from casino_commands import AuditView, AuditModal
        feature = CasinoFeature(None)
        feature.store = object()
        with patch.dict(os.environ, {'CASINO_AUDITOR_IDS': '123,456'}):
            entry = AuditView(feature, 123)
            foreign = interaction(456)
            await feature.act(foreign, entry, 'audit_game')
            self.assertFalse(foreign.response.send_modal.called)
            modal = AuditModal(entry, 'audit_game')
            modal.value._value = 'not-a-uuid'
            bad = interaction()
            await modal.on_submit(bad)
            self.assertFalse(bad.response.defer.called)
            modal.value._value = '00000000-0000-0000-0000-000000000001'
            with patch('casino_commands.CasinoRecords') as queries:
                queries.return_value.history = AsyncMock(return_value=Page((), False))
                guessed = interaction()
                await modal.on_submit(guessed)
                self.assertIn('沒有符合', guessed.followup.send.call_args.kwargs['embed'].description)
                async def revoked_while_reading(**kwargs):
                    os.environ['CASINO_AUDITOR_IDS'] = ''
                    return Page((), False)
                queries.return_value.history.side_effect = revoked_while_reading
                revoked = interaction()
                await modal.on_submit(revoked)
                self.assertNotIn('embed', revoked.followup.send.call_args.kwargs)
                self.assertTrue(revoked.followup.send.call_args.kwargs['ephemeral'])
