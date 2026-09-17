import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from poker_tests import test_table_web, test_multi_guild
from poker_tests.test_table_web import A, B, C
from poker.discord_api import Discord
import httpx

class AuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_allowlist_does_not_bypass_bot_guild_policy(self):
        config=replace(test_multi_guild.MultiGuildTests().config(), allowed_user_ids=('949256946572210256',))
        async with httpx.AsyncClient() as client:
            discord=Discord(config, client)
            discord.member=AsyncMock(return_value='absent')
            self.assertEqual(await discord.eligible('949256946572210256'),'member')
            discord.member.assert_not_awaited()
            self.assertEqual(await discord.eligible(A),'absent')
            self.assertEqual(await discord.member('949256946572210256'),'absent')
        with self.assertRaises(ValueError): replace(config,allowed_user_ids=('oops',)).validate()
        from poker.config import Config
        with patch.dict('os.environ',{'POKER_ALLOWED_USER_IDS':'949256946572210256, 949256946572210256'}):
            self.assertEqual(Config.from_env().allowed_user_ids,('949256946572210256',))

class AutoplayTests(unittest.TestCase):
    # Reuse fixtures without inheriting and rerunning the whole web suite.
    for name in ('setUp','headers','view','account','command','connect','join','advance','start_hand','act'):
        locals()[name]=getattr(test_table_web.TableWebTests,name)

    def test_autoplay_waits_one_second_folds_and_is_idempotent(self):
        self.join(A); self.join(B); hand=self.start_hand()
        actor=hand['players'][hand['actor']]['id']
        bank=self.account(actor)['time_bank']
        response,payload=self.command(actor,'set_autoplay',enabled=True)
        self.assertEqual(response.status_code,200,response.text)
        self.advance(.5)
        self.assertEqual(self.view()['hand']['turn'],hand['turn'])
        self.client.post('/api/table/commands',headers=self.headers(actor),json=payload)
        self.advance(.5)
        final=self.view(actor)
        self.assertIsNotNone(final['hand']['payouts'])
        action=[e for e in final['events'] if e['kind']=='action'][-1]
        self.assertEqual(action['action'],'fold')
        self.assertEqual(self.account(actor)['time_bank'],bank)
        self.assertTrue(next(m for m in final['members'] if m['id']==actor)['autoplay'])

    def test_check_and_cancel_before_due(self):
        self.join(A); self.join(B); hand=self.start_hand()
        actor=hand['players'][hand['actor']]['id']; self.act(actor,'call')
        hand=self.view()['hand']; actor=hand['players'][hand['actor']]['id']
        self.command(actor,'set_autoplay',enabled=True); self.advance(1)
        self.assertEqual([e for e in self.view()['events'] if e['kind']=='action'][-1]['action'],'check')
        self.command(actor,'set_autoplay',enabled=False)
        turn=self.view()['hand']['turn']; self.advance(1)
        self.assertEqual(self.view()['hand']['turn'],turn)
        self.assertFalse(next(m for m in self.view()['members'] if m['id']==actor)['autoplay'])

    def test_disconnect_keeps_autoplay_and_observer_cannot_control(self):
        socket=self.join(A); self.command(A,'set_autoplay',enabled=True); socket.close(); self.advance(180)
        self.assertTrue(self.view(A)['joined'])
        self.assertTrue(self.view(A)['members'][0]['autoplay'])
        response,_=self.command(B,'set_autoplay',enabled=True)
        self.assertEqual(response.status_code,409)

    def test_leave_preserves_final_presentation_but_spectator_gets_no_hidden_cards(self):
        self.join(A); self.join(B); hand=self.start_hand()
        actor=hand['players'][hand['actor']]['id']
        self.command(actor,'leave'); self.act(actor,'fold')
        state=self.view(actor)
        self.assertFalse(state['joined']); self.assertEqual(state['role'],'spectator')
        terminal=state['departure']; self.assertEqual(terminal['hand']['id'],hand['id'])
        self.assertTrue(any(m['id']==actor for m in terminal['members']))
        self.assertEqual(self.account(actor)['table'],'0')
        self.assertTrue(all(not p['cards'] for p in state['hand']['players']))
        self.assertEqual(state['hand']['legal'],{})
        denied,_=self.command(actor,'act',hand_id=hand['id'],turn=hand['turn'],action='check')
        self.assertEqual(denied.status_code,409)
        self.assertIsNone(self.view(C)['departure'])

    def test_private_former_member_can_watch_but_not_rejoin_without_invite(self):
        import uuid
        created=self.client.post('/api/tables',headers=self.headers(A),json={'command_id':uuid.uuid4().hex,'name':'Private','private':True,'amount':'2000'}).json()['state']
        tid=created['id']; self.connect(A)
        invitation=self.client.get('/api/table/invitation',headers=self.headers(A)).json()['invitation']
        def cmd(user,kind,**extra):
            view=self.client.get('/api/table',params={'table_id':tid},headers={**self.headers(user),'x-table-invitation':invitation}).json()
            return self.client.post('/api/table/commands',headers=self.headers(user),json={'command_id':uuid.uuid4().hex,'table_id':tid,'version':view['version'],'kind':kind,'control':self.controls.get(user),**extra})
        self.assertEqual(cmd(B,'join',amount='2000',invitation=invitation).status_code,200)
        self.connect(B); self.assertEqual(cmd(A,'leave').status_code,200)
        watched=self.client.get('/api/table',params={'table_id':tid},headers=self.headers(A))
        self.assertEqual(watched.status_code,200); self.assertEqual(watched.json()['role'],'spectator')
        self.assertEqual(cmd(A,'join',amount='2000').status_code,409)
        self.assertEqual(self.client.get('/api/table',params={'table_id':tid},headers=self.headers(C)).status_code,409)
        with self.client.websocket_connect('/ws/table?table_id='+tid,headers=self.headers(A)) as socket:
            self.assertEqual(socket.receive_json()['state']['id'],tid)
            socket.send_json({'type':'heartbeat'})
            self.assertEqual(socket.receive_json()['state']['role'],'spectator')

    def test_autoplay_crosses_hands_and_old_control_cannot_cancel(self):
        self.join(A); self.join(B); hand=self.start_hand()
        actor=hand['players'][hand['actor']]['id']
        self.command(actor,'set_autoplay',enabled=True); self.advance(1)
        final=self.view(actor); self.assertIsNotNone(final['hand']['payouts'])
        self.advance(.1); final=self.view(actor)
        self.advance(max(1,final['countdown']-self.now+.1))
        current=self.view(actor)
        self.assertNotEqual(current['hand']['id'],hand['id'])
        self.assertTrue(next(m for m in current['members'] if m['id']==actor)['autoplay'])
        response,_=self.command(actor,'set_autoplay',enabled=False,control='old-tab')
        self.assertEqual(response.status_code,409)
        self.assertTrue(next(m for m in self.view(actor)['members'] if m['id']==actor)['autoplay'])
        self.command(actor,'set_autoplay',enabled=False)
        self.assertFalse(next(m for m in self.view(actor)['members'] if m['id']==actor)['autoplay'])

    def test_cancel_after_automatic_action_preserves_accepted_fold(self):
        self.join(A); self.join(B); hand=self.start_hand()
        actor=hand['players'][hand['actor']]['id']
        self.command(actor,'set_autoplay',enabled=True); self.advance(1)
        before=self.view(actor)['hand']['payouts']
        response,_=self.command(actor,'set_autoplay',enabled=False)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.view(actor)['hand']['payouts'],before)
        actions=[e for e in self.view(actor)['events'] if e['kind']=='action' and e.get('action') not in ('small_blind','big_blind')]
        self.assertEqual(sum(e['action']=='fold' for e in actions),1); self.assertEqual(actions[-1]['action'],'fold')

    def test_set_autoplay_requires_boolean_and_sitout_stops_it(self):
        self.join(A)
        for extra in ({},{'enabled':None}):
            response,_=self.command(A,'set_autoplay',**extra)
            self.assertEqual(response.status_code,422)
        self.command(A,'set_autoplay',enabled=True)
        self.command(A,'sitout')
        self.assertFalse(self.view(A)['members'][0]['autoplay'])

    def test_allowlisted_oauth_and_recheck_without_admin_escalation(self):
        from urllib.parse import parse_qs, urlparse
        target='949256946572210256'
        self.app.state.discord.config=replace(self.config,allowed_user_ids=(target,))
        self.app.state.discord.member=AsyncMock(return_value='absent')
        def login(user):
            response=self.client.get('/auth/login',follow_redirects=False)
            state=parse_qs(urlparse(response.headers['location']).query)['state'][0]
            return self.client.get('/auth/callback',params={'code':user,'state':state},follow_redirects=False)
        self.assertEqual(login(target).status_code,303)
        self.tokens[target]=self.client.cookies.get('poker_session');self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/roles',headers=self.headers(target)).json(),{'tables':False,'funds':False})
        self.join(target)
        self.client.portal.call(self.app.state.scan.run,self.now+86400)
        self.assertEqual(self.client.get('/api/account',headers=self.headers(target)).status_code,200)
        self.assertEqual(login('999999999999999999').status_code,403)

    def test_all_in_side_pots_capture_terminal_stacks_and_release_seat(self):
        self.join(A,'2000');self.join(B,'3000');self.join(C,'4000');hand=self.start_hand()
        self.command(A,'leave')
        for _ in range(3):
            h=self.view()['hand']; actor=h['players'][h['actor']]['id']
            self.act(actor,'all_in' if self.view(actor)['hand']['legal']['raise'] else 'call')
        state=self.view(A); terminal=state['departure']
        self.assertFalse(state['joined']);self.assertEqual(terminal['hand']['id'],hand['id'])
        self.assertTrue(any(e['kind']=='all_in_reveal' for e in terminal['events']))
        self.assertTrue(any(e['kind']=='payout' for e in terminal['events']))
        self.assertGreaterEqual(len(terminal['hand']['settlement']['pots']),2)
        awarded=next(m for m in terminal['members'] if m['id']==A)['stack']
        self.assertEqual(int(self.account(A)['available']),48000+int(awarded))
        self.assertEqual(self.account(A)['table'],'0')
        self.advance(.1); countdown=self.view(B)['countdown']
        self.assertNotIn(A,[m['id'] for m in self.view(B)['members']])
        if countdown is not None:
            self.advance(countdown-self.now+.1)
            self.assertNotIn(A,[p['id'] for p in self.view(B)['hand']['players']])
