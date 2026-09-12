"""Pai Gow contracts: worked card examples, not an evaluator clone."""

import unittest

import paigow


def cards(text):
    ranks = 'A23456789TJQK'
    suits = 'shdc'
    return [52 if item == 'X' else suits.index(item[1]) * 13 + ranks.index(item[0])
            for item in text.split()]


class PaiGowRulesTests(unittest.TestCase):

    def test_resolved_joker_sorts_as_its_represented_card_without_replacing_ids(self):
        examples = [
            ('2s 3s 4s 5s X', '2s 3s 4s 5s X'),
            ('7h 7d 7c 7s X', '7s X 7h 7d 7c'),
            ('2h X', 'X 2h'),
            ('Ks Qs Js Ts X', 'X Ts Js Qs Ks'),
        ]
        for source, expected in examples:
            with self.subTest(source=source):
                hand = cards(source)
                original = hand.copy()
                joker = paigow.evaluate(hand).joker_as
                self.assertEqual(paigow.display_order(hand, joker_as=joker), cards(expected))
                self.assertEqual(paigow.display_order(hand)[-1], paigow.JOKER)
                self.assertEqual(hand, original)

    def test_joker_makes_any_pair_or_five_of_a_kind(self):
        self.assertEqual(paigow.evaluate(cards('Ks X')).score, (1, 13))
        five = paigow.evaluate(cards('7s 7h 7d 7c X'))
        self.assertEqual(five.score, (9, 7))
        self.assertGreater(five.score, paigow.evaluate(cards('As Ks Qs Js Ts')).score)


    def test_house_way_and_player_selection_are_legal_and_do_not_move_joker(self):
        hand = cards('As Ah Ks Kh 9d 6c X')
        front = paigow.house_way(hand)
        self.assertTrue(paigow.legal_split(hand, front))
        self.assertEqual(front, paigow.house_way(list(reversed(hand))))
        self.assertFalse(paigow.legal_split(cards('Ks X Qh 9d 7c 4h 2s'), cards('Ks X')))
        state = paigow.deal(list(range(53)))
        paigow.validate(state)
        paigow.act(state, 'auto')
        self.assertFalse(state['confirmed'])
        paigow.act(state, 'confirm')
        self.assertIn(paigow.result(state), ('win', 'loss', 'tie'))

    def test_wildcard_categories_wheel_kickers_and_cross_hand_order(self):
        examples = [
            ('7s 7h X 4c 2d', (3, 7, 4, 2)),
            ('7s 7h 4c 4d X', (6, 7, 4)),
            ('7s 7h 7d X 2c', (7, 7, 2)),
            ('2s 3h 4d 5c X', (4, 6)),
            ('2s 3s 4s 5s X', (8, 6)),
            ('As Ks 9s 7s X', (5, 14, 14, 13, 9, 7)),
        ]
        for hand, expected in examples:
            with self.subTest(hand=hand):
                self.assertEqual(paigow.evaluate(cards(hand)).score, expected)
        royal = paigow.evaluate(cards('As Kh Qd Jc Ts')).score
        wheel = paigow.evaluate(cards('As 2h 3d 4c 5s')).score
        king = paigow.evaluate(cards('Ks Qh Jd Tc 9s')).score
        self.assertGreater(royal, wheel)
        self.assertGreater(king, wheel)
        six = paigow.evaluate(cards('2s 3h 4d 5c 6s')).score
        self.assertGreater(six, wheel)
        self.assertEqual(wheel, (4, 5))
        self.assertEqual(royal, (4, 14))
        self.assertEqual(paigow.evaluate(cards('As 2s 3s 4s 5s')).score, (8, 5))
        self.assertEqual(paigow.evaluate(cards('As Ks Qs Js Ts')).score, (8, 14))
        self.assertGreater(paigow.evaluate(cards('Ks Kh Ad Jc 8s')).score,
                           paigow.evaluate(cards('Kd Kc As Jh 7s')).score)
        self.assertTrue(paigow.legal_split(cards('As Kh Ad Kc 8h 6d 2c'), cards('As Kh')))
        self.assertFalse(paigow.legal_split(cards('As Ah Ks Qh 9d 6c 2d'), cards('As Ah')))

    def test_each_front_back_comparison_treats_ties_neutrally(self):
        front = {-1: cards('2s 3h'), 0: cards('4s 5h'), 1: cards('6s 7h')}
        back = {-1: cards('2s 2h 3d 4c 7s'), 0: cards('8s 8h 3d 4c 7s'),
                1: cards('Ks Kh 3d 4c 7s')}
        expected = {(-1, -1): 'loss', (-1, 0): 'loss', (-1, 1): 'tie',
                    (0, -1): 'loss', (0, 0): 'tie', (0, 1): 'win',
                    (1, -1): 'tie', (1, 0): 'win', (1, 1): 'win'}
        for (a, b), result in expected.items():
            self.assertEqual(paigow.compare(front[a], back[b], front[0], back[0]), ((a, b), result))


    def test_supported_versions_preserve_saved_settlement_and_joker_choices(self):
        player = cards('4s 5s As 2h 3d 4c 5h')
        dealer = cards('4h 5d 2s 3h 4d 5c 6s')
        state = dict(rules=paigow.LEGACY_RULE_VERSION, player=player, dealer=dealer,
                     deck=[c for c in range(53) if c not in player + dealer],
                     front=player[:2], suggested_front=player[:2],
                     dealer_front=dealer[:2], confirmed=True)
        paigow.validate(state)
        self.assertEqual(paigow.result(state), 'tie')
        self.assertEqual(paigow.evaluate(cards('2s 3s 4s 5s X'),
                         rules=paigow.LEGACY_RULE_VERSION).joker_as, cards('As')[0])
        state['rules'] = paigow.RULE_VERSION
        paigow.validate(state)
        self.assertEqual(paigow.result(state), 'loss')
        self.assertEqual(paigow.evaluate(cards('2s 3s 4s 5s X')).joker_as, cards('6s')[0])
        low, high = cards('4s 5h'), cards('8s 8h 3d 4c 7s')
        self.assertEqual(paigow.compare(low, high, low, high,
                         rules=paigow.LEGACY_RULE_VERSION)[1], 'loss')
        self.assertEqual(paigow.compare(low, high, low, high)[1], 'tie')

    def test_all_straights_and_straight_flushes_increase_from_five_to_ace(self):
        runs = ['A2345', '23456', '34567', '45678', '56789', '6789T',
                '789TJ', '89TJQ', '9TJQK', 'TJQKA']
        for suits, category in [('shdcs', 4), ('sssss', 8)]:
            scores = [paigow.evaluate(cards(' '.join(r+s for r, s in zip(run, suits)))).score
                      for run in runs]
            self.assertEqual(scores, [(category, high) for high in range(5, 15)])

    def test_house_way_decision_table(self):
        examples = [
            ('As Kh Qd 9c 7s 4h 2d', 'Kh Qd'),
            ('Ks Kh Ad Jc 8s 5h 2d', 'Ad Jc'),
            ('Ks Kh 4s 4h Ad 9c 2d', 'Ad 9c'),
            ('Ks Kh Qs Qh Ad 9c 2d', 'Qs Qh'),
            ('Ks Kh 8s 8h Ad 9c 2d', '8s 8h'),
            ('Ks Kh 4s 4h 9d 6c 2d', '4s 4h'),
            ('Ks Kh 8s 8h 4d 4c 2d', 'Ks Kh'),
            ('7s 7h 7d Ac Kd 4c 2s', 'Ac Kd'),
            ('As Ah Ad Kc 9d 4c 2s', 'As Kc'),
            ('Ks Kh Kd 7s 7h 2c 4d', '7s 7h'),
            ('Ks Kh Kd 7s 7h 7c 2d', 'Ks Kh'),
            ('Ks Kh Kd 7s 7h 4c 4d', '7s 7h'),
            ('2s 2h 2d 2c As Kh 7d', 'As Kh'),
            ('8s 8h 8d 8c As Kh 2d', 'As Kh'),
            ('8s 8h 8d 8c Ks Qh 2d', '8s 8h'),
            ('Js Jh Jd Jc As Kh 2d', 'Js Jh'),
            ('Js Jh Jd Jc 2s 2h Ad', '2s 2h'),
            ('7s 7h 7d 7c X 2s 3h', '7s 7h'),
            ('As Ah Ad Ac X Ks Kh', 'Ks Kh'),
            ('2s 3h 4d 5c 6s Kh Qd', 'Kh Qd'),
            ('2s 3h 4d 5c 6s Kh Kd', 'Kh Kd'),
            ('2s 4s 6s 8s Ts Kh Qd', 'Kh Qd'),
            ('2s 3s 4s 5s 6s Kh Qd', 'Kh Qd'),
            ('2s 3s 4s 5s 6s 7h 8d', '7h 8d'),
            ('2s 3s 4s 5s X Kh Qd', 'Kh Qd'),
            ('As Ah Ks Kh 9d 6c X', 'As Ah'),
            ('7s 7h X Ac Kd 4c 2s', 'Ac Kd'),
            ('2s 4h 6d 8c Ts Kh X', 'Kh Ts'),
        ]
        for hand, expected in examples:
            with self.subTest(hand=hand):
                self.assertEqual(set(paigow.house_way(cards(hand))), set(cards(expected)))
                self.assertTrue(paigow.legal_split(cards(hand), paigow.house_way(cards(hand))))

    def test_invalid_selections_and_persisted_state_are_rejected(self):
        from copy import deepcopy
        from casino_rules import CasinoError
        state = paigow.deal(list(range(53)))
        for selection in (None, [], [0], [0, 0], [0, 1], [True, 2], [0, 2, 4]):
            with self.assertRaises(CasinoError):
                paigow.act(state, 'select', selection)
            self.assertEqual(state['front'], [])
        for key, value in (('rules', 'unknown'), ('deck', []), ('confirmed', True),
                           ('player', [True] * 7), ('dealer_front', [1, 1]),
                           ('suggested_front', []), ('front', [0, 0])):
            corrupted = deepcopy(state)
            corrupted[key] = value
            with self.assertRaises(ValueError):
                paigow.validate(corrupted)

    def test_house_way_is_legal_deterministic_and_uses_only_its_own_cards(self):
        import random
        randomizer = random.Random(11)
        for _ in range(120):
            hand = randomizer.sample(range(53), 7)
            chosen = paigow.house_way(hand)
            self.assertTrue(paigow.legal_split(hand, chosen))
            randomizer.shuffle(hand)
            self.assertEqual(paigow.house_way(hand), chosen)


if __name__ == '__main__':
    unittest.main()
