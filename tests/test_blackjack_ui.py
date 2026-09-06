"""Public interaction and image delivery contracts."""

import asyncio
import io
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from casino_commands import CasinoFeature, LobbyView
from casino_rules import Bet
from casino_store import Game
from test_casino_ui import interaction


def hand():
    return Game(uuid4(), 123, Bet(100), 100, [], 'active', None, 0, 900, 1, False,
                'blackjack', (0, 4), (8, None), datetime(2026, 9, 6, tzinfo=timezone.utc))


class BlackjackUITests(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_acknowledges_before_waiting_for_existing_action(self):
        feature = CasinoFeature(None)
        event = interaction()
        lock = feature.owner_lock(123)
        pending = None
        try:
            async with lock:
                pending = asyncio.create_task(feature.slash(event))
                await asyncio.sleep(0)
                self.assertTrue(event.response.defer.called)
        finally:
            if pending is not None:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def test_dice_fallback_contains_each_face_and_total(self):
        feature = CasinoFeature(None)
        event = interaction()
        game = replace(hand(), game='dice', status='settled', dice=[6, 6, 6, 1, 2, 3], outcome='win')
        with patch.object(feature, 'table_image', new=AsyncMock(side_effect=OSError('injected failure'))):
            await feature.show_result(event, game)
        text = event.edit_original_response.call_args.kwargs['embed'].description
        self.assertIn('6 · 6 · 6', text)
        self.assertIn('1 · 2 · 3', text)
        self.assertIn('總和 18', text)
        self.assertIn('總和 6', text)

    async def test_each_lobby_open_selects_from_all_six_mei_images(self):
        from pathlib import Path
        feature = CasinoFeature(None)
        event = interaction()
        selections = []
        captured = []
        def choose(paths):
            selections.append(tuple(paths))
            return paths[len(selections) - 1]
        async def delivered(**kwargs):
            captured.append(kwargs['attachments'][0].fp.read())
        event.edit_original_response.side_effect = delivered
        with patch('casino_commands.secrets.choice', side_effect=choose):
            for _ in range(2):
                await feature.render(event, __import__('discord').Embed(description='Lobby'), LobbyView(feature, 123), dealer=True)
        self.assertEqual(len(selections), 2)
        self.assertEqual({Path(p).name for p in selections[0]}, {f'Mei ({i}).jpg' for i in range(1, 7)})
        self.assertNotEqual(captured[0], captured[1])

    async def test_background_expiry_updates_original_message_once(self):
        game = hand()
        result = replace(game, status='settled', outcome='tie', returned=100, dealer=(8, 20), version=2, deadline=None)
        store = SimpleNamespace(expire_pending=AsyncMock(return_value=[result]))
        feature = CasinoFeature(store)
        event = interaction()
        await feature.show_result(event, game)
        event.edit_original_response.reset_mock()
        await feature.expire_once()
        self.assertEqual(event.edit_original_response.call_args.kwargs['view'].game, result)
        store.expire_pending.return_value = []
        await feature.expire_once()
        self.assertEqual(event.edit_original_response.await_count, 1)

    async def test_slow_old_image_cannot_overwrite_new_result(self):
        feature = CasinoFeature(None)
        event = interaction()
        event.message = SimpleNamespace(id=456)
        old = hand()
        newest = replace(old, version=3, status='settled', outcome='win', dealer=(8, 20), returned=200)
        started, release = asyncio.Event(), asyncio.Event()
        async def render(game):
            if game.version == 1:
                started.set()
                await release.wait()
            return b'image'
        with patch.object(feature, 'table_image', side_effect=render):
            slow = asyncio.create_task(feature.show_result(event, old))
            await started.wait()
            await feature.show_result(event, newest)
            release.set()
            await slow
            await feature.show_result(event, old)
        self.assertEqual(event.edit_original_response.call_args.kwargs['view'].game.version, 3)
        self.assertEqual(event.edit_original_response.await_count, 1)

    async def test_table_images_are_decodable_for_cards_and_dice(self):
        from PIL import Image
        feature = CasinoFeature(None)
        for game in (hand(), replace(hand(), game='dice', status='settled', dice=[6, 6, 6, 1, 2, 3], outcome='win')):
            payload = await feature.table_image(game)
            image = Image.open(io.BytesIO(payload))
            self.assertEqual(image.size, (1200, 800))
            image.verify()

    async def test_playable_blackjack_and_hidden_card_text_fallback(self):
        from casino_commands import PlayView
        feature = CasinoFeature(None)
        game = hand()
        event = interaction()
        with patch.object(feature, 'table_image', new=AsyncMock(side_effect=OSError('render failed'))):
            await feature.show_result(event, game)
        reply = event.edit_original_response.call_args.kwargs
        self.assertIsInstance(reply['view'], PlayView)
        self.assertEqual([b.action for b in reply['view'].children], ['hit', 'stand', 'double'])
        self.assertIn('暗牌', reply['embed'].description)
        self.assertIn('16', reply['embed'].description)
        self.assertEqual(reply['attachments'], [])
        self.assertFalse(LobbyView(feature, 123).children[0].disabled)
        stranger = interaction(456)
        await feature.act(stranger, reply['view'], 'double')
        self.assertTrue(stranger.response.send_message.call_args.kwargs['ephemeral'])
