import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
from reward_commands import RewardFeature, RewardError, parse_reward, ROLE_IDS, THRESHOLD
from reward_store import Grant


def member(uid, roles=(), bot=False):
    return NS(id=uid,_roles=list(roles),display_name=str(uid),bot=bot)


def message(text='reward <@2> 100'):
    guild=NS(id=10,fetch_member=AsyncMock(),fetch_roles=AsyncMock())
    guild.fetch_member.side_effect=lambda uid: member(uid,ROLE_IDS if uid==1 else ())
    return NS(id=100,content=text,guild=guild,author=member(1),webhook_id=None,
              channel=NS(id=20,send=AsyncMock()))


class RewardTests(unittest.IsolatedAsyncioTestCase):
    def feature(self):
        store=NS(find=AsyncMock(return_value=None),grant=AsyncMock(return_value=Grant(100,1,100)),
                 account_ids=AsyncMock(return_value=[1,2,3,4,5,6]))
        return RewardFeature(store)

    def test_parser(self):
        for text in ('reward <@2> 100','reward <@!2> 100'):
            self.assertEqual(parse_reward(text),(2,100))
        self.assertEqual(parse_reward('reward all 999'),('all',999))
        for text in ('reward','reward all','reward all 0','reward all -1','reward all 1.5',
                     'reward all 1e3','reward all 100abc','reward 2 10','reward <@0> 10','reward all 10 extra'):
            with self.subTest(text=text), self.assertRaises(RewardError): parse_reward(text)

    async def test_both_roles_and_no_operator_bonus(self):
        for role in ROLE_IDS:
            f=self.feature(); m=message()
            m.guild.fetch_member.side_effect=lambda uid: member(uid,[role] if uid==1 else [])
            await f.on_message(m)
            f.store.grant.assert_awaited_once_with(100,1,10,20,'single',100,{2:'2'})
            m.channel.send.assert_awaited_once()
        f=self.feature(); m=message('reward <@!1> 100')
        await f.on_message(m)
        self.assertEqual(f.store.grant.call_args.args[-1],{1:'1'})

    async def test_denied_and_ignored_messages(self):
        f=self.feature(); m=message()
        m.guild.fetch_member.side_effect=lambda uid: NS(_roles=[],guild_permissions=NS(administrator=True))
        await f.on_message(m)
        f.store.find.assert_not_awaited()
        self.assertIn('GM',m.channel.send.call_args.args[0])
        for field,value in [('guild',None),('webhook_id',99),('content','/reward <@2> 100'),('author',member(1,bot=True))]:
            f=self.feature(); m=message(); setattr(m,field,value)
            await f.on_message(m)
            f.store.find.assert_not_awaited(); m.channel.send.assert_not_awaited()

    async def test_all_eligibility_and_four_request_limit(self):
        f=self.feature(); m=message('reward all 100')
        m.guild.fetch_roles.return_value=[NS(id=8,name=THRESHOLD,position=10,hoist=True),
                                         NS(id=9,name='high',position=11,hoist=True),
                                         NS(id=7,name='low',position=9,hoist=True),
                                         NS(id=6,name='unhoisted',position=99,hoist=False)]
        active=0; peak=0
        async def fetch(uid):
            nonlocal active,peak
            active+=1; peak=max(peak,active)
            try:
                await asyncio.sleep(.005)
                if uid==5: raise discord.NotFound(NS(status=404,reason='missing'),{'code':10007,'message':'missing'})
                return member(uid,{1:[8],2:[9],3:[7],4:[6],6:[]}[uid],bot=uid==2)
            finally: active-=1
        m.guild.fetch_member.side_effect=fetch
        result=await f.recipients(m.guild,'all')
        self.assertEqual(result,{1:'1',2:'2'}); self.assertLessEqual(peak,4)
        f.store.account_ids.assert_awaited_once()

    async def test_missing_threshold_empty_or_http_error_never_grants(self):
        f=self.feature(); m=message('reward all 100'); m.guild.fetch_roles.return_value=[]
        await f.on_message(m); f.store.grant.assert_not_awaited()
        f=self.feature(); m=message('reward all 100')
        m.guild.fetch_roles.return_value=[NS(id=8,name=THRESHOLD,position=10,hoist=True)]
        await f.on_message(m); f.store.grant.assert_not_awaited()
        self.assertEqual(m.channel.send.call_args.args[0],'沒有符合資格的成員')
        f=self.feature(); m=message('reward all 100')
        m.guild.fetch_roles.side_effect=discord.Forbidden(NS(status=403,reason='denied'),'denied')
        await f.on_message(m); f.store.grant.assert_not_awaited()

    async def test_revocation_before_write(self):
        f=self.feature(); m=message()
        m.guild.fetch_member.side_effect=[member(1,ROLE_IDS),member(2),member(1)]
        await f.on_message(m); f.store.grant.assert_not_awaited()

    async def test_duplicate_and_delivery_failure_do_not_repeat_grant(self):
        f=self.feature(); m=message()
        f.store.find.return_value=Grant(100,1,100)
        await f.on_message(m); f.store.grant.assert_not_awaited()
        f=self.feature(); m=message()
        m.channel.send.side_effect=discord.HTTPException(NS(status=500,reason='failed'),'failed')
        await f.on_message(m); f.store.grant.assert_awaited_once()

    async def test_member_query_failure_cancels_batch(self):
        for error in (discord.HTTPException(NS(status=500,reason='failed'),'failed'),
                      discord.NotFound(NS(status=404,reason='guild'),{'code':10004,'message':'Unknown Guild'})):
            f=self.feature(); m=message('reward all 100')
            m.guild.fetch_roles.return_value=[NS(id=8,name=THRESHOLD,position=10,hoist=True)]
            async def fetch(uid):
                if uid==1: return member(1,ROLE_IDS | {8})
                if uid==3: raise error
                await asyncio.sleep(.01)
                return member(uid,[8])
            m.guild.fetch_member.side_effect=fetch
            await f.on_message(m)
            f.store.grant.assert_not_awaited()

    async def test_bot_routes_reward_without_registering_command(self):
        from bot import create_bot
        client=create_bot()
        async with client:
            client.crystals.on_message=AsyncMock()
            client.rewards.on_message=AsyncMock()
            m=message()
            await client.on_message(m)
            client.crystals.on_message.assert_awaited_once_with(m)
            client.rewards.on_message.assert_awaited_once_with(m)
            self.assertNotIn('reward',[c.name for c in client.tree.get_commands()])
