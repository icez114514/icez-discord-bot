import copy
import unittest
from poker import rules
from poker.replay import frames


class AllInPresentationTests(unittest.TestCase):
    def finish_all_in(self, sizes):
        hand = rules.create([(str(i), size) for i, size in enumerate(sizes)], 0, "reveal-test")
        while hand["actor"] is not None:
            rules.act(hand, hand["players"][hand["actor"]]["id"], "all_in")
        return hand

    def test_two_to_six_players_reveal_before_runout_and_replay(self):
        for count in range(2, 7):
            with self.subTest(count=count):
                hand = self.finish_all_in([1000] * count)
                events = hand["presentation"]
                reveal = next(i for i, e in enumerate(events) if e["kind"] == "all_in_reveal")
                self.assertEqual(sum(e["kind"] == "all_in_reveal" for e in events), 1)
                self.assertLess(reveal, next(i for i,e in enumerate(events) if e["kind"] == "board"))
                self.assertEqual(sum(hand["payouts"].values()), count * 1000)
                replay = frames(hand, "0")
                early = next(f for f in replay if f["event"]["kind"] == "all_in_reveal")
                self.assertEqual(early["board"], [])
                self.assertTrue(all(len(p["cards"]) == 2 for p in early["players"]))
                self.assertTrue(all(p["cards"] == [] for p in replay[0]["players"] if p["id"] != "0"))

    def test_pending_call_and_two_able_players_do_not_reveal(self):
        hand = rules.create([("a",1000),("b",2000),("c",2000)],0,"pending")
        rules.act(hand,"a","all_in")
        self.assertFalse(any(e["kind"]=="all_in_reveal" for e in hand["presentation"]))
        rules.act(hand,"b","call")
        rules.act(hand,"c","call")
        self.assertEqual(hand["street"],"flop")
        self.assertFalse(any(e["kind"]=="all_in_reveal" for e in hand["presentation"]))

    def test_flop_lock_and_folded_cards_remain_private(self):
        hand = rules.create([("a",1000),("b",1000),("c",1000)],0,"flop")
        rules.act(hand,"a","fold")
        rules.act(hand,"b","call")
        rules.act(hand,"c","check")
        rules.act(hand,"b","all_in")
        rules.act(hand,"c","call")
        event = next(e for e in hand["presentation"] if e["kind"]=="all_in_reveal")
        self.assertEqual(event["street"],"flop")
        self.assertEqual(set(event["cards"]),{"b","c"})
        replay = frames(hand,"b")
        self.assertTrue(all(next(p for p in f["players"] if p["id"]=="a")["cards"]==[] for f in replay))

    def test_side_pots_refunds_and_invalid_reveal(self):
        hand = self.finish_all_in([101,201,301,501])
        self.assertGreater(len(hand["pots"]),1)
        self.assertGreater(sum(hand["refunds"].values()),0)
        frames(hand,"0")
        bad = copy.deepcopy(hand)
        event = next(e for e in bad["presentation"] if e["kind"]=="all_in_reveal")
        event["cards"]["0"]=["As","As"]
        with self.assertRaisesRegex(ValueError,"invalid_all_in_reveal"):
            frames(bad,"0")
        bad = copy.deepcopy(hand)
        event = next(e for e in bad["presentation"] if e["kind"]=="all_in_reveal")
        bad["presentation"].remove(event)
        bad["presentation"].insert(1,event)
        with self.assertRaises(ValueError):
            frames(bad,"0")

    def test_old_recordings_without_early_reveal_still_work(self):
        hand = self.finish_all_in([1000,1000])
        hand["presentation"]=[e for e in hand["presentation"] if e["kind"]!="all_in_reveal"]
        frames(hand,"0")

    def test_fold_win_does_not_reveal(self):
        hand=rules.create([("a",1000),("b",1000)],0,"fold")
        rules.act(hand,"a","fold")
        self.assertFalse(any(e["kind"]=="all_in_reveal" for e in hand["presentation"]))
        frames(hand,"a")
