import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import discord
from crystal_commands import CrystalFeature
from database import Account


class RankingNamesTests(unittest.IsolatedAsyncioTestCase):
    async def test_ten_current_names_and_username_fallback_in_rank_order(self):
        store=NS(leaderboard=AsyncMock(return_value=[Account(100+i,1000-i,'stale-other-guild') for i in range(10)]),claim=AsyncMock())
        active=0; peak=0
        async def fetch(uid):
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            try:
                await asyncio.sleep(.001)
                if uid in (101,102):
                    raise discord.NotFound(NS(status=404,reason='missing'),{'code':10007,'message':'missing'})
                return NS(display_name='nickname-'+str(uid-100))
            finally: active-=1
        async def user(uid):
            if uid==102: raise discord.HTTPException(NS(status=500,reason='failed'),'failed')
            return NS(name='username-fallback',global_name='not-username')
        guild=NS(fetch_member=AsyncMock(side_effect=fetch))
        client=NS(fetch_user=AsyncMock(side_effect=user))
        embed=await CrystalFeature(store).render(NS(), 'rank',guild=guild,client=client)
        self.assertEqual(len(embed.fields),10)
        self.assertIn('nickname-0',embed.fields[0].value)
        self.assertIn('username-fallback',embed.fields[1].value)
        self.assertIn('名稱暫時無法取得',embed.fields[2].value)
        self.assertIn('nickname-9',embed.fields[9].value)
        self.assertNotIn('stale-other-guild',str(embed.to_dict()))
        self.assertNotIn('102',embed.fields[2].value)
        self.assertLessEqual(peak,4)
        self.assertEqual(client.fetch_user.await_count,2)
        store.claim.assert_not_awaited()
