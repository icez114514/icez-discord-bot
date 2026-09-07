import asyncio
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from casino_commands import CasinoFeature, ResultView, PlayView
from casino_store import Game
from casino_rules import Bet
from test_casino_ui import interaction


def game(uid=123):
    return Game(uuid4(), uid, Bet(100), 100, [2,2,5,6,6,4], 'settled', 'win', 200, 1100, 1, False)


class ClickGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_replay_during_ack_is_not_queued(self):
        feature = CasinoFeature(AsyncMock())
        result = game()
        feature.store.replay.return_value = result
        feature.show_result = AsyncMock()
        view = ResultView(feature, 123, result)
        entered, release = asyncio.Event(), asyncio.Event()
        first, second = interaction(), interaction()
        async def delay_ack():
            entered.set()
            await release.wait()
        first.response.defer.side_effect = delay_ack
        task = asyncio.create_task(feature.act(first, view, 'replay'))
        try:
            await entered.wait()
            await asyncio.wait_for(feature.act(second, view, 'replay'), 1)
            second.response.defer.assert_awaited_once()
            feature.store.replay.assert_not_awaited()
            feature.show_result.assert_not_awaited()
        finally:
            release.set()
            await task
        feature.store.replay.assert_awaited_once()
        feature.show_result.assert_awaited_once()
        await feature.act(interaction(), view, 'replay')
        self.assertEqual(feature.store.replay.await_count, 2)

    async def test_mixed_clicks_during_render_are_dropped_and_other_owner_runs(self):
        feature = CasinoFeature(AsyncMock())
        result = game()
        feature.store.play.return_value = result
        entered, release = asyncio.Event(), asyncio.Event()
        async def render(event, result):
            if event.user.id == 123:
                entered.set()
                await release.wait()
        feature.show_result = AsyncMock(side_effect=render)
        view = PlayView(feature, 123, result)
        first = asyncio.create_task(feature.act(interaction(), view, 'hit'))
        try:
            await entered.wait()
            for action in ('hit', 'stand', 'double'):
                await asyncio.wait_for(feature.act(interaction(), view, action), 1)
            feature.store.play.assert_awaited_once()
            other = game(456)
            await asyncio.wait_for(feature.act(interaction(456), PlayView(feature,456,other), 'stand'), 1)
            self.assertEqual(feature.store.play.await_count, 2)
        finally:
            release.set()
            await first

    async def test_cancellation_releases_guard(self):
        feature = CasinoFeature(AsyncMock())
        result = game()
        feature.store.replay.return_value = result
        feature.show_result = AsyncMock()
        view = ResultView(feature,123,result)
        entered = asyncio.Event()
        async def pending():
            entered.set()
            await asyncio.Event().wait()
        event = interaction()
        event.response.defer.side_effect = pending
        task = asyncio.create_task(feature.act(event,view,'replay'))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await feature.act(interaction(),view,'replay')
        feature.store.replay.assert_awaited_once()

    async def test_ack_failure_releases_guard_and_stranger_cannot_act(self):
        feature = CasinoFeature(AsyncMock())
        result = game()
        feature.store.replay.return_value = result
        feature.show_result = AsyncMock()
        view = ResultView(feature,123,result)
        await feature.act(interaction(456),view,'replay')
        feature.store.replay.assert_not_awaited()
        event=interaction()
        event.response.defer.side_effect=RuntimeError('injected acknowledgement failure')
        with self.assertRaises(RuntimeError):
            await feature.act(event,view,'replay')
        await feature.act(interaction(),view,'replay')
        feature.store.replay.assert_awaited_once()
