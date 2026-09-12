"""Owner-facing Pai Gow text flow and safe card projections."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import paigow
from casino_commands import CasinoFeature, LobbyView
from casino_rules import Bet
from casino_store import Game
from test_casino_ui import interaction
from test_paigow import cards


def hand():
    player = tuple(cards('As Ah Ks Kh 9d 6c X'))
    return Game(uuid4(), 123, Bet(100), 100, [], 'active', None, 0, 900, 1, False,
                'paigow', player, (None,) * 7, datetime(2026, 9, 12, tzinfo=timezone.utc),
                tuple(paigow.house_way(player)), (), paigow.RULE_VERSION)


class PaiGowUITests(unittest.IsolatedAsyncioTestCase):
    async def test_text_fallback_preserves_selection_and_hides_dealer(self):
        from casino_commands import PaiGowView
        feature, event, game = CasinoFeature(None), interaction(), hand()
        with patch.object(feature, 'table_image', new=AsyncMock(side_effect=OSError('image unavailable'))):
            await feature.show_result(event, game)
            await __import__('asyncio').gather(*feature.image_tasks, return_exceptions=True)
        reply = event.edit_original_response.call_args.kwargs
        self.assertIsInstance(reply['view'], PaiGowView)
        self.assertIn('前墩', reply['embed'].description)
        self.assertIn('後墩', reply['embed'].description)
        self.assertIn('Joker', reply['embed'].description)
        self.assertIn('暗牌', reply['embed'].description)
        self.assertEqual(reply['attachments'], [])
        selector = reply['view'].children[0]
        self.assertEqual((selector.min_values, selector.max_values, len(selector.options)), (2, 2, 7))
        self.assertEqual({int(o.value) for o in selector.options if o.default}, set(game.front))
        stranger = interaction(456)
        await feature.act(stranger, reply['view'], 'pai_confirm')
        self.assertTrue(stranger.response.send_message.call_args.kwargs['ephemeral'])
        self.assertIn('paigow', [b.action for b in LobbyView(feature, 123).children])

    async def test_images_show_both_split_hands_and_a_real_joker_sprite(self):
        import io
        from PIL import Image
        from casino_images import TableRenderer
        feature, game = CasinoFeature(None), hand()
        dealer = tuple(cards('2s 2h 3s 3h 5d 8c Td'))
        completed = replace(game, status='settled', outcome='tie', dealer=dealer,
                            dealer_front=tuple(paigow.house_way(dealer)), returned=100, version=3)
        for sample in (replace(game, front=()), game, completed):
            payload = await feature.table_image(sample)
            image = Image.open(io.BytesIO(payload))
            self.assertEqual(image.size, (1200, 1800))
            image.verify()
        renderer = TableRenderer('casino_assets')
        self.assertIn(52, renderer.cards)
        self.assertNotEqual(renderer.cards[52].tobytes(), renderer.cards[0].tobytes())

    async def test_old_image_does_not_replace_new_selection(self):
        import asyncio
        feature, event, original = CasinoFeature(None), interaction(), hand()
        event.message = SimpleNamespace(id=456)
        newest = replace(original, version=2, front=())
        started, release = asyncio.Event(), asyncio.Event()
        async def image(game):
            if game.version == 1:
                started.set()
                await release.wait()
            return b'preview'
        with patch.object(feature, 'table_image', side_effect=image):
            pending = asyncio.create_task(feature.show_result(event, original))
            await started.wait()
            await feature.show_result(event, newest)
            release.set()
            await pending
            await __import__('asyncio').gather(*feature.image_tasks, return_exceptions=True)
        previews = [call.kwargs for call in event.edit_original_response.call_args_list if 'view' in call.kwargs]
        self.assertEqual([p['view'].game.version for p in previews], [1, 2])
        self.assertEqual(previews[-1]['view'].game, newest)
        self.assertTrue(event.edit_original_response.call_args.kwargs['attachments'])
        self.assertNotIn('view', event.edit_original_response.call_args.kwargs)
        await feature.stop_background()


    async def test_inflight_image_finishes_before_new_preview(self):
        import asyncio
        feature, event, original = CasinoFeature(None), interaction(), hand()
        event.message = SimpleNamespace(id=456)
        accepted, release, next_preview = asyncio.Event(), asyncio.Event(), asyncio.Event()
        applied, remote_tasks = [], []
        original_preview = feature.preview_paigow

        async def preview(*args):
            if args[3].version == 2:
                next_preview.set()
            return await original_preview(*args)

        async def remote_edit(**kwargs):
            version = int(kwargs['embed'].footer.text.rsplit(' ', 1)[-1])
            kind = 'preview' if 'view' in kwargs else 'image'
            if version == 1 and kind == 'image':
                async def finish_accepted_request():
                    accepted.set()
                    await release.wait()
                    applied.append((version, kind))
                remote = asyncio.create_task(finish_accepted_request())
                remote_tasks.append(remote)
                # Cancelling a client wait cannot undo an accepted Discord PATCH.
                await asyncio.shield(remote)
            else:
                applied.append((version, kind))

        event.edit_original_response.side_effect = remote_edit
        with patch.object(feature, 'table_image', new=AsyncMock(return_value=b'preview')), \
                patch.object(feature, 'preview_paigow', side_effect=preview):
            await feature.show_result(event, original)
            await asyncio.wait_for(accepted.wait(), 2)
            old_image = next(iter(feature.image_tasks))
            pending = asyncio.create_task(feature.show_result(event, replace(original, version=2, front=())))
            try:
                await asyncio.wait_for(next_preview.wait(), 2)
                # Let a cancellation, if incorrectly requested, reach the HTTP waiter.
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                cancelled = old_image.cancelled()
            finally:
                release.set()
                await pending
                await asyncio.gather(*remote_tasks, *feature.image_tasks, return_exceptions=True)
                await feature.stop_background()
        self.assertFalse(cancelled, 'An accepted image edit must retain the delivery lock')
        self.assertEqual(applied, [(1, 'preview'), (1, 'image'), (2, 'preview'), (2, 'image')])

    async def test_upload_failure_preserves_full_text_and_controls(self):
        import discord
        feature, event = CasinoFeature(None), interaction()
        event.edit_original_response.side_effect = [
            None, discord.HTTPException(SimpleNamespace(status=500, reason='test'), 'upload failed')]
        await feature.show_result(event, hand())
        reply = event.edit_original_response.call_args.kwargs
        await __import__('asyncio').gather(*feature.image_tasks, return_exceptions=True)
        self.assertEqual(event.edit_original_response.await_count, 2)
        self.assertEqual(reply['attachments'], [])
        self.assertIn('Joker', reply['embed'].description)
        self.assertIn('前墩', reply['embed'].description)
        self.assertFalse(reply['view'].children[-1].disabled)

    async def test_active_renderer_does_not_leak_even_an_unmasked_dealer(self):
        feature, game = CasinoFeature(None), hand()
        # Defense in depth: renderer hides active dealer cards regardless of caller.
        self.assertEqual(await feature.table_image(game),
                         await feature.table_image(replace(game, dealer=tuple(range(7)),
                                                          dealer_front=(0, 1))))

    async def test_selected_preview_is_visible_before_slow_image_finishes(self):
        import asyncio
        feature, event = CasinoFeature(None), interaction()
        started, release = asyncio.Event(), asyncio.Event()
        async def slow_image(game):
            started.set()
            await release.wait()
            return b'preview'
        with patch.object(feature, 'table_image', side_effect=slow_image):
            pending = asyncio.create_task(feature.show_result(event, hand()))
            try:
                await asyncio.wait_for(started.wait(), 2)
                self.assertTrue(event.edit_original_response.called,
                                'Selected hand preview is blocked behind image generation')
                self.assertIn('前墩', event.edit_original_response.call_args.kwargs['embed'].description)
                await asyncio.wait_for(asyncio.shield(pending), 0.5)
            finally:
                release.set()
                await pending
                await feature.stop_background()

    async def test_selector_text_and_picture_indices_follow_ace_to_king(self):
        from casino_commands import PaiGowView, paigow_description
        game = replace(hand(), player=tuple(cards('Kh 2d As Ah Qs 9c X')), front=())
        view = PaiGowView(CasinoFeature(None), 123, game)
        self.assertEqual([option.value for option in view.children[0].options],
                         list(map(str, cards('As Ah 2d 9c Qs Kh X'))))
        self.assertIn('1:A♠ · 2:A♥ · 3:2♦', paigow_description(game))
