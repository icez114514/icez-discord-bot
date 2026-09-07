import unittest
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4
from casino_commands import CasinoFeature, SettingsView, ResultView, PlayView
from casino_rules import Bet, InsufficientBalance
from casino_store import Preferences, SettingsSnapshot
from test_blackjack_ui import hand
from test_casino_ui import interaction


class BalanceNoticeTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_wagers_edit_main_message_without_replacing_cards(self):
        for action in ('start','replay','double'):
            with self.subTest(action=action):
                store=AsyncMock()
                feature=CasinoFeature(store)
                game=hand()
                prefs=Preferences(Bet(100),None,None,uuid4())
                view=(SettingsView(feature,123,prefs) if action=='start' else
                      ResultView(feature,123,game) if action=='replay' else PlayView(feature,123,game))
                method=store.play if action=='double' else getattr(store,action)
                method.side_effect=InsufficientBalance('水晶餘額不足')
                event=interaction()
                await feature.act(event,view,action)
                event.edit_original_response.assert_awaited_once()
                kwargs=event.edit_original_response.call_args.kwargs
                self.assertIn('餘額不足',kwargs['content'])
                self.assertNotIn('attachments',kwargs)
                self.assertNotIn('view',kwargs)
                event.followup.send.assert_not_awaited()

    async def test_settings_and_result_have_balance_notice(self):
        feature=CasinoFeature(None)
        feature.render=AsyncMock(return_value=True)
        prefs=Preferences(Bet(100),None,None,uuid4())
        await feature.show_settings(interaction(),SettingsSnapshot(prefs,50))
        self.assertIn('餘額不足',feature.render.call_args.args[1].description)
        await feature.show_settings(interaction(),SettingsSnapshot(prefs,100))
        self.assertIsNone(feature.render.call_args.args[1].description)
        for status in ('active','settled'):
            game=replace(hand(),status=status,balance_after=50, dealer=(8,None) if status=='active' else (8,20))
            await feature.show_result(interaction(),game)
            embed=feature.render.call_args.args[1]
            self.assertTrue(any('餘額不足' in f.value for f in embed.fields))
