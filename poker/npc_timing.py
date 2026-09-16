"""Human-paced NPC turns, independent of private cards or the chosen action."""

import random


def think_seconds(hand, rng=None):
    """Overlapping 1..4.7s distributions leave headroom before the 5s deadline.

    Public decision pressure (street, opponents and price relative to pot) shifts
    the mode. It never keys off hole cards, hand strength or the eventual action.
    """
    rng = rng or random.SystemRandom()
    player = hand["players"][hand["actor"]]
    opponents = sum(not p["folded"] and p["id"] != player["id"] for p in hand["players"])
    price = max(0, hand["current_bet"] - player["bet"])
    pot = max(1, sum(p["paid"] for p in hand["players"]))
    street = {"preflop": 0, "flop": 0.5, "turn": 0.8, "river": 1.0}[hand["street"]]
    pressure = min(1.0, price / pot)
    mode = min(4.4, 1.3 + street + 0.3 * max(0, opponents - 1) + 1.4 * pressure)
    return rng.triangular(1.0, 4.7, mode)
