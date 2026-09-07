"""Scoring/display contracts captured from the original mei-bot gamble.js."""
import json
import unittest
from itertools import permutations, product
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import ImageDraw
from casino_images import TableRenderer
from casino_rules import Bet, dice_points, outcome
from casino_store import Game

CASES = json.loads((Path(__file__).parent / "fixtures/mei_dice_points.json").read_text(encoding="utf-8"))["cases"]

class DiceScoringTests(unittest.TestCase):
    def test_all_original_scores_in_every_order(self):
        for case in CASES:
            for dice in set(permutations(case["dice"])):
                self.assertEqual(dice_points(dice), case["points"], dice)

    def test_all_original_outcomes(self):
        for left, right in product(CASES, repeat=2):
            a = (left["points"], sum(left["dice"]))
            b = (right["points"], sum(right["dice"]))
            expected = "win" if a > b else "loss" if a < b else "tie"
            self.assertEqual(outcome(left["dice"], right["dice"]), expected)

    def test_image_uses_points_not_sum(self):
        renderer = TableRenderer("missing-test-assets")
        game = Game(uuid4(), 123, Bet(100), 100, [2,2,5,6,6,4], "settled", "win", 200, 1100, 1, False)
        texts = []
        original = ImageDraw.ImageDraw.text
        def capture(draw, xy, text, *args, **kwargs):
            texts.append(text)
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, "text", capture):
            renderer.render(game)
        self.assertIn("YOU  /  5", texts)
        self.assertIn("DEALER  /  4", texts)
