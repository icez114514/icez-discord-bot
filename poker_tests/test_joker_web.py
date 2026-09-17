import unittest
import uuid
from poker_tests.test_table_web import TableWebTests,A,B,C

class JokerWebTests(TableWebTests):
    def create_joker(self, private=False, command_id=None):
        response=self.client.post('/api/tables',headers=self.headers(A),json={'command_id':command_id or uuid.uuid4().hex,'name':'Jokers','private':private,'amount':'2000','game_mode':'double_joker'})
        self.assertEqual(response.status_code,200,response.text)
        self.table_id=response.json()['state']['id']
        return response
    def command(self,user,kind,**extra):
        return super().command(user,kind,**{'table_id':getattr(self,'table_id','main'),**extra})
    def test_mode_is_immutable_and_creation_is_idempotent(self):
        cid=uuid.uuid4().hex; first=self.create_joker(command_id=cid)
        self.assertEqual(self.create_joker(command_id=cid).json()['state']['id'],self.table_id)
        self.assertEqual(first.json()['state']['game_mode'],'double_joker')
        self.assertEqual(self.client.get('/api/tables',headers=self.headers(B)).json()['tables'][0]['game_mode'],'double_joker')
        response,payload=self.command(A,'topup',amount='100',game_mode='standard')
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.view()['game_mode'],'double_joker')
        self.assertEqual(self.client.post('/api/tables',headers=self.headers(B),json={'command_id':'bad-mode','name':'bad','amount':'2000','game_mode':'bad'}).status_code,422)
    def test_private_preview_exposes_mode_without_private_cards(self):
        self.create_joker(private=True); self.connect(A)
        invitation=self.client.get('/api/table/invitation',headers=self.headers(A)).json()['invitation']
        r=self.client.get('/api/table',params={'table_id':self.table_id},headers={**self.headers(B),'x-table-invitation':invitation})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['game_mode'],'double_joker');self.assertNotIn('hand',r.json())
        self.assertNotIn('members',r.json())
    def test_joker_hand_recovers_and_replays(self):
        self.create_joker(); self.connect(A)
        self.assertEqual(self.command(B,'join',amount='2000',version=self.view()['version'])[0].status_code,200)
        self.connect(B); before=self.start_hand()
        self.restart(); after=self.view()['hand']
        self.assertEqual(after['id'],before['id']);self.assertEqual(after['game_mode'],'double_joker')
        self.assertEqual(after['players'],before['players']);self.assertFalse(self.view()['frozen'])
        self.connect(A);self.connect(B)
        for _ in range(10):
            hand=self.view()['hand']
            if hand['payouts'] is not None:break
            actor=hand['players'][hand['actor']]['id'];self.act(actor,'all_in')
        self.assertIsNotNone(self.view()['hand']['payouts'])
        result=self.client.get('/api/hands/'+before['id'],headers=self.headers(A)).json()
        self.assertTrue(result['complete'],result);self.assertEqual(result['game_mode'],'double_joker')
        self.assertTrue(all(f['game_mode']=='double_joker' for f in result['frames']))
        spectator=self.client.get('/api/table',params={'table_id':self.table_id},headers=self.headers(C)).json()
        self.assertFalse(spectator['joined']);self.assertFalse(spectator['control'])
    def test_joker_npc_plays_real_ledger(self):
        self.create_joker();self.connect(A)
        self.assertEqual(self.command(A,'add_npc')[0].status_code,200)
        self.start_hand()
        for _ in range(30):
            hand=self.wait_hand(lambda h:h['payouts'] is not None or h['players'][h['actor']]['id']==A)
            if hand['payouts'] is not None:break
            self.act(A,'check' if self.view()['hand']['legal']['check'] else 'call')
        else:self.fail('joker NPC never settled')
        self.assertEqual(sum(int(m['stack']) for m in self.view()['members']),12000)
        npc=next(m for m in self.view()['members'] if m['id'].startswith('npc:'))
        self.assertEqual(npc['npc_failures'],0)

def load_tests(loader,tests,pattern):
    return unittest.TestSuite(JokerWebTests(n) for n in JokerWebTests.__dict__ if n.startswith('test_'))