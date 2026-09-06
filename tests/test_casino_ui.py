import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord import app_commands

from casino_commands import CasinoFeature, LobbyView, SettingsView, BetModal
from casino_store import Preferences
from casino_rules import Bet
from uuid import uuid4


def interaction(user_id=123):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, bot=False), guild=SimpleNamespace(id=1),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock(), send_modal=AsyncMock(), is_done=lambda: False),
        followup=SimpleNamespace(send=AsyncMock()), edit_original_response=AsyncMock(),
    )


class CasinoUITests(unittest.IsolatedAsyncioTestCase):
    async def test_lobby_has_two_games_and_owner_guard(self):
        feature = CasinoFeature(None)
        view = LobbyView(feature, 123)
        self.assertEqual([b.label for b in view.children], ['21 點', '18 豆仔'])
        self.assertFalse(view.children[0].disabled)
        stranger = interaction(456)
        self.assertFalse(await view.interaction_check(stranger))
        self.assertTrue(stranger.response.send_message.call_args.kwargs['ephemeral'])
        self.assertTrue(await view.interaction_check(interaction()))
        client = discord.Client(intents=discord.Intents.none())
        tree = app_commands.CommandTree(client)
        feature.register(tree)
        self.assertEqual([c.name for c in tree.get_commands()], ['賭場'])

    async def test_custom_modal_rechecks_owner_and_prefills_last_custom(self):
        feature = CasinoFeature(None)
        prefs = Preferences(Bet(50, 2), 246, 13, uuid4())
        view = SettingsView(feature, 123, prefs)
        modal = BetModal(view, 'base')
        self.assertEqual(modal.amount.default, '246')
        stranger = interaction(456)
        await modal.on_submit(stranger)
        self.assertTrue(stranger.response.send_message.call_args.kwargs['ephemeral'])
        self.assertFalse(stranger.response.defer.called)
    async def test_dealer_upload_failure_falls_back_without_financial_action(self):
        import tempfile
        from pathlib import Path
        feature = CasinoFeature(None)
        event = interaction()
        error = discord.HTTPException(SimpleNamespace(status=500, reason='test'), 'upload failed')
        event.edit_original_response.side_effect = [error, None]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dealer.jpg'
            path.write_bytes(b'placeholder image bytes')
            feature.dealer_path = str(path)
            await feature.render(event, discord.Embed(description='Lobby'), LobbyView(feature, 123), dealer=True)
        self.assertEqual(event.edit_original_response.call_args.kwargs['attachments'], [])
        self.assertIsNone(event.edit_original_response.call_args.kwargs['embed'].image.url)

    async def test_blank_dealer_setting_uses_bundled_asset(self):
        from unittest.mock import patch
        import os
        with patch.dict(os.environ, {'CASINO_DEALER_IMAGE': ''}):
            self.assertEqual(CasinoFeature(None).dealer_path, '')