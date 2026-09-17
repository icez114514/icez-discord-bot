import itertools
import random
import time
import unittest
from poker import rules, replay
from poker.wildcards import CARDS,JOKERS,deck_for,evaluate
from poker.joker_npc import decide,choose_action
from poker.npc import observation

class JokerTests(unittest.TestCase):
    def test_categories_and_substitutions(self):
        cases=[('As Ks Qs Js Xr 2d 3c',(8,14)),('As 2s 3s Xr Xb 9d Tc',(8,5)),('As Ah Ad Xr Xb 2d 3c',(7,14,13)),('As Ah Xr Kd Kc 2s 3c',(6,14,13)),('As Js 8s 4s Xr 2d 3c',(5,14,13,11,8,4)),('4d Xr 3h 6c 5h 7d 2h',(4,8)),('As Ah Ad Ac Xr Xb 2s',(7,14,13))]
        for text,expected in cases:
            cards=text.split();actual=evaluate(cards,True)
            self.assertEqual(actual['score'],expected,text)
            self.assertEqual(len(actual['cards']),5)
            concrete=[actual['substitutions'].get(c,c) for c in actual['cards']]
            self.assertEqual(len(set(concrete)),5)
            self.assertEqual(rules.strength(concrete),expected,text)
            self.assertTrue(set(actual['cards'])<=set(cards))
    def test_independent_enumeration_oracle(self):
        rng=random.Random(948)
        for n in (0,1,2):
            for _ in range(8):
                real=rng.sample(CARDS,7-n); cards=real+list(JOKERS[:n])
                expected=max(rules.strength(real+list(extra)) for extra in itertools.combinations([c for c in CARDS if c not in real],n))
                self.assertEqual(evaluate(cards),expected,cards)
    def test_deck_projection_and_replay(self):
        for mode,count in [('standard',52),('double_joker',54)]:
            for players in range(2,7):
                hand=rules.create([(str(i),2000) for i in range(players)],0,'test',mode)
                dealt=hand['deck']+[c for p in hand['players'] for c in p['cards']]
                self.assertEqual(len(set(dealt)),count)
                projected=rules.project(hand,'0')
                self.assertEqual(projected['game_mode'],mode)
                self.assertTrue(all(not p['cards'] and p['best_hand'] is None for p in projected['players'] if p['id']!='0'))
                while hand['payouts'] is None:
                    rules.act(hand,hand['players'][hand['actor']]['id'],'all_in')
                frames=replay.frames(hand,'0')
                self.assertTrue(all(f['game_mode']==mode for f in frames))
                self.assertEqual(sum(hand['payouts'].values()),sum(p['paid'] for p in hand['players']))
    def test_side_pots_refunds_and_ties(self):
        hand=rules.create([('a',100),('b',200),('c',300)],0,'side','double_joker')
        hand['board']=['Ah','Ad','7c','8d','2s']
        for p,cards,paid in zip(hand['players'],[['Xr','3c'],['Ks','Kh'],['Qs','Qh']],[100,200,300]):
            p.update(cards=cards,paid=paid,stack=0,bet=paid,folded=False)
        rules.finish(hand)
        self.assertEqual(hand['payouts'],{'a':300,'b':200,'c':100})
        self.assertEqual(hand['refunds']['c'],100)
        hand['board']=['Ts','Js','Qs','Ks','Xr']
        for p,cards in zip(hand['players'],[['Xb','2d'],['As','3c'],['9s','4c']]):p['cards']=cards
        rules.finish(hand)
        self.assertEqual(hand['payouts'],{'a':100,'b':200,'c':300})

    def test_replay_rejects_mode_mismatch_and_duplicate_joker(self):
        import copy
        hand=rules.create([('a',2000),('b',2000)],0,'invalid','double_joker')
        rules.act(hand,'a','fold')
        replay.frames(hand,'a')
        wrong=copy.deepcopy(hand);wrong['game_mode']='standard'
        with self.assertRaises(ValueError):replay.frames(wrong,'a')
        wrong=copy.deepcopy(hand);wrong['deck'][0]='Xr';wrong['deck'][1]='Xr'
        with self.assertRaises(ValueError):replay.frames(wrong,'a')

    def test_public_joker_independent_substitution_and_tie(self):
        board=['Xr','Ts','Js','Qs','Ks']
        self.assertEqual(evaluate(['2h','3h']+board),evaluate(['2c','3c']+board))
        self.assertEqual(evaluate(['As','Ah']+['Xr','Ad','2h','3c','7d']),(7,14,7))
    def test_npc_observation_is_private_and_decision_is_legal(self):
        hand=rules.create([('a',2000),('b',500),('c',1000)],0,'npc','double_joker')
        state=observation(hand)
        self.assertNotIn('deck',state)
        self.assertTrue(all('cards' not in p for p in state['players']))
        start=time.monotonic(); decision=decide(state,rng=random.Random(1))
        self.assertLess(time.monotonic()-start,1.3)
        rules.act(hand,hand['players'][hand['actor']]['id'],decision['action'],decision.get('amount'))
    def test_npc_thresholds_and_timeout(self):
        hand=rules.create([('a',2000),('b',2000)],0,'npc','double_joker');s=observation(hand)
        self.assertEqual(choose_action(s,0,200)['action'],'fold')
        self.assertEqual(choose_action(s,.6,200)['action'],'call')
        self.assertEqual(choose_action(s,.9,200)['action'],'raise')
        ticks=iter([0,2]);self.assertEqual(decide(s,clock=lambda:next(ticks)),{'action':'fold'})
        s['can_check']=True;self.assertEqual(choose_action(s,0,200)['action'],'check')

if __name__=='__main__':unittest.main()