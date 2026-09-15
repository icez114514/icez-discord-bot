import unittest

from poker import rules
from poker.store import Conflict


class RulesTests(unittest.TestCase):
    def test_dealing_rejects_invalid_participant_rosters(self):
        for players in (
            [("a", 1000)],
            [("a", 1000), ("a", 2000)],
            [("a", 0), ("b", 1000)],
            [(str(i), 1000) for i in range(7)],
        ):
            with self.subTest(players=players), self.assertRaises(Conflict):
                rules.create(players, 0, "hand")

    def test_cumulative_short_all_ins_reopen_each_player_individually(self):
        hand = rules.create(
            [(str(i), n) for i, n in enumerate((200, 1000, 1000, 1000, 150, 1000))],
            0,
            "h",
        )
        rules.act(hand, "3", "call")
        rules.act(hand, "4", "all_in")
        rules.act(hand, "5", "call")
        rules.act(hand, "0", "all_in")
        rules.act(hand, "1", "call")
        rules.act(hand, "2", "call")
        self.assertEqual(hand["actor"], 3)
        self.assertTrue(rules.legal(hand)["raise"])
        rules.act(hand, "3", "call")
        self.assertEqual(hand["actor"], 5)
        self.assertFalse(rules.legal(hand)["raise"])
        with self.assertRaisesRegex(Conflict, "raise_not_allowed"):
            rules.act(hand, "5", "all_in")
        self.assertEqual(hand["players"][5]["stack"], 850)
        rules.act(hand, "5", "call")
        self.assertEqual(hand["street"], "flop")

    def test_multiway_side_pots_and_uncalled_refund_are_conserved(self):
        from unittest.mock import patch

        # Four overpairs: aces win the main pot, kings the first side pot,
        # queens the next, and jacks receive only their unmatched 200.
        draw = [
            "Ks",
            "Qs",
            "Js",
            "As",
            "Kd",
            "Qd",
            "Jd",
            "Ad",
            "5c",
            "2c",
            "3d",
            "4h",
            "6c",
            "8s",
            "7c",
            "9c",
        ]

        def shuffle(deck):
            deck[:] = [c for c in rules.CARDS if c not in draw] + list(reversed(draw))

        with patch("secrets.SystemRandom.shuffle", side_effect=shuffle):
            hand = rules.create(
                [("a", 101), ("b", 201), ("c", 301), ("d", 501)], 0, "h"
            )
        for user in ("d", "a", "b", "c"):
            rules.act(hand, user, "all_in")
        self.assertEqual(hand["payouts"], {"a": 404, "b": 300, "c": 200, "d": 200})
        self.assertEqual(hand["refunds"]["d"], 200)
        self.assertEqual(hand["board"], ["2c", "3d", "4h", "8s", "9c"])

    def test_split_pot_odd_chip_goes_to_winner_left_of_button(self):
        from unittest.mock import patch

        draw = [
            "2c",
            "3c",
            "4c",
            "2d",
            "3d",
            "4d",
            "5c",
            "Th",
            "Jh",
            "Qh",
            "6c",
            "Kh",
            "7c",
            "Ah",
        ]

        def shuffle(deck):
            deck[:] = [c for c in rules.CARDS if c not in draw] + list(reversed(draw))

        with patch("secrets.SystemRandom.shuffle", side_effect=shuffle):
            hand = rules.create([("a", 1000), ("b", 1000), ("c", 1000)], 0, "h")
        rules.act(hand, "a", "raise", 201)
        rules.act(hand, "b", "call")
        rules.act(hand, "c", "call")
        rules.act(hand, "b", "check")
        rules.act(hand, "c", "check")
        rules.act(hand, "a", "raise", 100)
        rules.act(hand, "b", "call")
        rules.act(hand, "c", "fold")
        for _ in range(2):
            rules.act(hand, "b", "check")
            rules.act(hand, "a", "check")
        self.assertEqual(hand["payouts"], {"a": 401, "b": 402, "c": 0})

    def test_short_blinds_run_out_when_no_decision_is_needed(self):
        hand = rules.create([("a", 25), ("b", 2000)], 0, "h")
        self.assertIsNone(hand["actor"])
        self.assertEqual(len(hand["board"]), 5)
        self.assertEqual(hand["refunds"]["b"], 75)
        self.assertEqual(sum(hand["payouts"].values()), 125)
        hand = rules.create([("a", 1000), ("b", 1000), ("c", 20)], 0, "h2")
        self.assertEqual(hand["actor"], 0)
        self.assertEqual(rules.legal(hand)["call"], 100)

    def test_heads_up_position_and_hand_ranking(self):
        hand = rules.create([("a", 1000), ("b", 1000)], 0, "h")
        self.assertEqual(hand["actor"], 0)
        rules.act(hand, "a", "call")
        rules.act(hand, "b", "check")
        self.assertEqual(hand["street"], "flop")
        self.assertEqual(hand["actor"], 1)
        self.assertEqual(
            rules.strength(["As", "Ks", "Qs", "Js", "Ts", "2c", "3d"]), (8, 14)
        )
        self.assertEqual(
            rules.strength(["Ac", "2d", "3s", "4h", "5c", "Kd", "Qd"]), (4, 5)
        )
