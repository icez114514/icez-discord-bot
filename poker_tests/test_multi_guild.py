import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import AsyncMock, patch
import httpx
from poker.config import Config
from poker.discord_api import Discord

class MultiGuildTests(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return Config(data_dir=Path.cwd(), environment='test', origin='http://testserver', client_id='123', guild_id='456', additional_guild_ids=('345198011275673601',), client_secret='s'*32, bot_token='b'*32, reader_token='r'*32, funds_token='f'*32)

    async def test_membership_is_union_and_errors_are_not_departure(self):
        for first, second, expected in [('member','absent','member'),('absent','member','member'),('retry','member','member'),('absent','absent','absent'),('absent','retry','retry'),('retry','absent','retry')]:
            with self.subTest(first=first,second=second):
                async with httpx.AsyncClient() as client:
                    discord=Discord(self.config(),client)
                    discord._member_in_guild=AsyncMock(side_effect=[first,second])
                    self.assertEqual(await discord.member('111'),expected)
                    self.assertEqual(discord._member_in_guild.await_count,1 if first=='member' else 2)

    async def test_second_guild_member_and_all_confirmed_absent(self):
        for joined in (True,False):
            visited=[]
            def transport(request):
                visited.append(request.url.path)
                if '/members/' in request.url.path:
                    if joined and '/345198011275673601/' in request.url.path:
                        return httpx.Response(200,json={'user':{'id':'111'}})
                    return httpx.Response(404,json={'code':10007})
                return httpx.Response(200,json={})
            async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
                result=await Discord(self.config(),client).member('111')
                self.assertEqual(result,'member' if joined else 'absent')
                self.assertIn('/api/v10/guilds/345198011275673601/members/111',visited)

    def test_config_keeps_primary_deduplicates_and_validates(self):
        config=self.config();config.validate()
        self.assertEqual(replace(config,additional_guild_ids=('456','789','789')).allowed_guild_ids,('456','789'))
        with self.assertRaises(ValueError): replace(config,additional_guild_ids=('not-an-id',)).validate()
        with patch.dict('os.environ',{'POKER_GUILD_ID':'456','POKER_ADDITIONAL_GUILD_IDS':' 789, 345198011275673601, '}):
            self.assertEqual(Config.from_env().allowed_guild_ids,('456','789','345198011275673601'))
