import unittest
from unittest.mock import patch

from poker import rules
from poker.statistics import calculate, metric_view


def finish(hand):
    while hand["payouts"] is None:
        user = hand["players"][hand["actor"]]["id"]
        rules.act(hand, user, "check" if rules.legal(hand)["check"] else "call")
    return calculate(hand)


class FormulaTests(unittest.TestCase):
    def test_walk_blinds_and_automatic_fold_are_valid_without_vpip(self):
        hand = rules.create([("a", 2000), ("b", 2000)], 0, "walk")
        rules.act(hand, "a", "fold", automatic=True)
        stats = calculate(hand)
        self.assertEqual(stats["a"]["net_win"], [0, 1])
        self.assertEqual(stats["b"]["net_win"], [1, 1])
        for user in ("a", "b"):
            self.assertEqual(stats[user]["vpip"], [0, 1])
            self.assertEqual(stats[user]["pfr"], [0, 1])
            self.assertEqual(stats[user]["wsd"], [0, 0])
        self.assertTrue(hand["history"][-1]["automatic"])

    def test_small_blind_completion_and_forced_all_in(self):
        hand = rules.create([("a", 2000), ("b", 2000)], 0, "limp")
        rules.act(hand, "a", "call")
        stats = finish(hand)
        self.assertEqual(stats["a"]["vpip"], [1, 1])
        self.assertEqual(stats["b"]["vpip"], [0, 1])
        self.assertEqual(stats["a"]["cbet"], [0, 0])
        stats = calculate(rules.create([("a", 25), ("b", 2000)], 0, "blind"))
        self.assertEqual(stats["a"]["vpip"], [0, 1])
        self.assertEqual(stats["a"]["wsd"][1], 1)
        self.assertEqual(stats["b"]["three_bet"], [0, 0])

    def test_short_all_in_counts_raise_but_does_not_reopen(self):
        hand = rules.create([("a", 2000), ("b", 250), ("c", 2000)], 0, "short")
        rules.act(hand, "a", "raise", 200)
        rules.act(hand, "b", "all_in")
        rules.act(hand, "c", "fold", automatic=True)
        self.assertFalse(rules.legal(hand)["raise"])
        rules.act(hand, "a", "call")
        stats = calculate(hand)
        self.assertEqual(stats["b"]["pfr"], [1, 1])
        self.assertEqual(stats["b"]["three_bet"], [1, 1])
        self.assertEqual(stats["c"]["fold_three_bet"], [1, 1])
        self.assertEqual(stats["a"]["fold_three_bet"], [0, 1])
        self.assertEqual(stats["a"]["three_bet"], [0, 0])
        self.assertEqual(stats["a"]["cbet"], [0, 0])

    def test_call_only_all_in_and_four_bet_do_not_add_three_bet_opportunity(self):
        hand = rules.create([("a", 2000), ("b", 150), ("c", 2000)], 0, "call")
        rules.act(hand, "a", "raise", 300)
        rules.act(hand, "b", "all_in")
        rules.act(hand, "c", "raise", 600)
        rules.act(hand, "a", "raise", 1000)
        rules.act(hand, "c", "fold")
        stats = finish(hand)
        self.assertEqual(stats["b"]["pfr"], [0, 1])
        self.assertEqual(stats["b"]["three_bet"], [0, 0])
        self.assertEqual(stats["c"]["three_bet"], [1, 1])
        self.assertEqual(stats["c"]["fold_three_bet"], [0, 0])
        self.assertEqual(stats["a"]["fold_three_bet"], [0, 1])

    def test_cbet_requires_first_flop_action_without_lead(self):
        for lead in (False, True):
            hand = rules.create([("a", 2000), ("b", 2000)], 0, str(lead))
            rules.act(hand, "a", "raise", 300)
            rules.act(hand, "b", "call")
            rules.act(hand, "b", "raise" if lead else "check", 100 if lead else None)
            rules.act(hand, "a", "raise", 300 if lead else 100)
            stats = finish(hand)
            self.assertEqual(stats["a"]["cbet"], [0, 0] if lead else [1, 1])
        hand = rules.create([("a", 2000), ("b", 2000)], 0, "skip")
        rules.act(hand, "a", "raise", 300)
        rules.act(hand, "b", "call")
        stats = finish(hand)
        self.assertEqual(stats["a"]["cbet"], [0, 1])

    def test_side_pot_winner_with_net_loss_and_refund_only_loser(self):
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
                [("a", 101), ("b", 201), ("c", 301), ("d", 501)], 0, "side"
            )
        for user in ("d", "a", "b", "c"):
            rules.act(hand, user, "all_in")
        stats = calculate(hand)
        self.assertEqual(hand["payouts"]["c"] - 301, -101)
        self.assertEqual(stats["c"]["net_win"], [0, 1])
        self.assertEqual(stats["c"]["wsd"], [1, 1])
        self.assertEqual(stats["d"]["wsd"], [0, 1])
        self.assertEqual(stats["d"]["cbet"], [0, 0])

    def test_zero_denominator_and_thresholds(self):
        self.assertEqual(metric_view(0, 0, 20)["percent"], "—")
        self.assertEqual(metric_view(0, 1, 100)["percent"], "0.0%")
        self.assertEqual(metric_view(1, 3, 100)["percent"], "33.3%")
        self.assertTrue(metric_view(1, 19, 20)["low_sample"])
        self.assertFalse(metric_view(1, 20, 20)["low_sample"])

    def test_shared_board_split_counts_wsd_but_not_net_win(self):
        draw = ["2c", "3c", "2d", "3d", "5c", "Th", "Jh", "Qh", "6c", "Kh", "7c", "Ah"]

        def shuffle(deck):
            deck[:] = [c for c in rules.CARDS if c not in draw] + list(reversed(draw))

        with patch("secrets.SystemRandom.shuffle", side_effect=shuffle):
            hand = rules.create([("a", 100), ("b", 100)], 0, "split")
        rules.act(hand, "a", "call")
        stats = calculate(hand)
        self.assertEqual(hand["payouts"], {"a": 100, "b": 100})
        for user in ("a", "b"):
            self.assertEqual(stats[user]["wsd"], [1, 1])
            self.assertEqual(stats[user]["net_win"], [0, 1])
        self.assertTrue(metric_view(1, 99, 100)["low_sample"])
        self.assertFalse(metric_view(1, 100, 100)["low_sample"])
