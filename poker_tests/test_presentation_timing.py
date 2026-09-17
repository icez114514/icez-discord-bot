import unittest
from poker.presentation import event_duration, publish_hand, next_hand_delay

class PresentationTimingTests(unittest.TestCase):
    def test_all_in_runout_survives_publish_batches(self):
        table={'id':'t','hand':{'id':'h','players':[{},{}], 'presentation':[{'kind':'all_in_reveal'}]}}
        publish_hand(table,100)
        self.assertAlmostEqual(table['presentation_end'],100.7)
        table['hand']['presentation'].append({'kind':'board'})
        publish_hand(table,100.1)
        self.assertAlmostEqual(table['presentation_end'],102.7)
        publish_hand(table,100.2)
        self.assertAlmostEqual(table['presentation_end'],102.7)

    def test_next_hand_waits_for_multi_pot_awards_and_result_hold(self):
        table={'id':'t','hand':{'id':'h','players':[{}]*6,'presentation':[{'kind':kind} for kind in ['all_in_reveal','board','board','board','showdown']+['payout']*18+['complete']]}}
        publish_hand(table,100)
        table['last']=table.pop('hand')
        self.assertAlmostEqual(next_hand_delay(table,100),table['presentation_end']+4.4+.5)
        self.assertEqual(next_hand_delay({'last':{}},100),105)
        self.assertEqual(next_hand_delay({'last':{'id':'h'}},100),105.5)
        self.assertEqual(event_duration({'kind':'board'},6),.65)
        self.assertEqual(event_duration({'kind':'board'},6,True),2)

    def test_fold_finish_halves_wait_without_shortening_award_flights(self):
        hand={'id':'h','payouts':{'a':100},'showdown':False,'players':[{'folded':False},{'folded':True}]}
        self.assertAlmostEqual(next_hand_delay({'last':hand,'presentation_end':100.3},100),102.75)
        self.assertAlmostEqual(next_hand_delay({'last':hand,'presentation_end':104},100),106.45)
        hand['showdown']=True
        self.assertAlmostEqual(next_hand_delay({'last':hand,'presentation_end':100.3},100),105.5)
        hand['showdown']=False;hand['void']=True
        self.assertAlmostEqual(next_hand_delay({'last':hand,'presentation_end':100.3},100),105.5)
