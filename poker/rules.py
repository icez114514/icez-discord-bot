"""Private, serializable no-limit hold'em state; callers persist before publishing."""

import secrets
from collections import Counter
from itertools import combinations

from .store import Conflict

CARDS = tuple(r + s for r in "23456789TJQKA" for s in "cdhs")
STREETS = ("preflop", "flop", "turn", "river")


def strength(cards):
    """Comparable best-five score, including the ace-low straight."""

    def five(hand):
        ranks = sorted(("23456789TJQKA".index(c[0]) + 2 for c in hand), reverse=True)
        groups = sorted(((n, r) for r, n in Counter(ranks).items()), reverse=True)
        unique = sorted(set(ranks), reverse=True)
        straight = (
            (5 if unique == [14, 5, 4, 3, 2] else unique[0])
            if len(unique) == 5
            and (unique[0] - unique[-1] == 4 or unique == [14, 5, 4, 3, 2])
            else 0
        )
        flush = len({c[1] for c in hand}) == 1
        if straight and flush:
            return (8, straight)
        if groups[0][0] == 4:
            return (7, groups[0][1], groups[1][1])
        if [g[0] for g in groups] == [3, 2]:
            return (6, groups[0][1], groups[1][1])
        if flush:
            return (5, *ranks)
        if straight:
            return (4, straight)
        if groups[0][0] == 3:
            return (3, *(r for _, r in groups))
        if [g[0] for g in groups][:2] == [2, 2]:
            return (2, *(r for _, r in groups))
        if groups[0][0] == 2:
            return (1, *(r for _, r in groups))
        return (0, *ranks)

    return max(five(hand) for hand in combinations(cards, 5))


def clockwise(hand, after):
    n = len(hand["players"])
    return [(after + i) % n for i in range(1, n + 1)]


def create(players, button, hand_id):
    """Production always uses OS-backed randomness. No seed/deck input."""
    if (
        not 2 <= len(players) <= 6
        or len({user for user, _ in players}) != len(players)
        or type(button) is not int
        or not 0 <= button < len(players)
        or any(
            not isinstance(user, str)
            or not user
            or type(stack) is not int
            or stack <= 0
            for user, stack in players
        )
    ):
        raise Conflict("invalid_participants")
    deck = list(CARDS)
    secrets.SystemRandom().shuffle(deck)
    hand = {
        "id": hand_id,
        "players": [],
        "button": button,
        "deck": deck,
        "board": [],
        "street": "preflop",
        "current_bet": 100,
        "increment": 100,
        "actor": None,
        "turn": 0,
        "history": [],
        "payouts": None,
        "refunds": {},
        "showdown": False,
    }
    for user, stack in players:
        hand["players"].append(
            {
                "id": user,
                "start": stack,
                "stack": stack,
                "bet": 0,
                "paid": 0,
                "cards": [],
                "folded": False,
                "acted_at": None,
                "reopen": 100,
            }
        )
    for _ in range(2):
        for i in clockwise(hand, button):
            hand["players"][i]["cards"].append(hand["deck"].pop())
    sb = button if len(players) == 2 else (button + 1) % len(players)
    bb = (sb + 1) % len(players)
    for i, blind in ((sb, 50), (bb, 100)):
        paid = min(blind, hand["players"][i]["stack"])
        contribute(hand["players"][i], paid)
        hand["history"].append(
            {
                "seat": i,
                "street": "preflop",
                "action": "small_blind" if i == sb else "big_blind",
                "amount": paid,
                "automatic": True,
            }
        )
    advance(hand, bb)
    return hand


def contribute(player, chips):
    player["stack"] -= chips
    player["bet"] += chips
    player["paid"] += chips


def legal(hand):
    if hand["actor"] is None or hand["payouts"] is not None:
        return {}
    p = hand["players"][hand["actor"]]
    owed = max(0, hand["current_bet"] - p["bet"])
    reopened = (
        p["acted_at"] is None or hand["current_bet"] - p["acted_at"] >= p["reopen"]
    )
    opponents = any(
        not q["folded"] and q["stack"] > 0 for q in hand["players"] if q is not p
    )
    maximum = p["bet"] + p["stack"]
    return {
        "fold": True,
        "check": owed == 0,
        "call": min(owed, p["stack"]),
        "raise": reopened and opponents and maximum > hand["current_bet"],
        "min_raise_to": 100
        if hand["current_bet"] < 100
        else hand["current_bet"] + hand["increment"],
        "max_raise_to": maximum,
    }


def act(hand, user, action, target=None, automatic=False):
    choices = legal(hand)
    if not choices or hand["players"][hand["actor"]]["id"] != user:
        raise Conflict("not_your_turn")
    actor = hand["actor"]
    p = hand["players"][actor]
    chips = 0
    if action == "all_in":
        if choices["max_raise_to"] > hand["current_bet"]:
            action, target = "raise", choices["max_raise_to"]
        else:
            action = "call"
    if action == "fold":
        p["folded"] = True
    elif action == "check":
        if not choices["check"]:
            raise Conflict("cannot_check")
    elif action == "call":
        if not choices["call"]:
            raise Conflict("nothing_to_call")
        chips = choices["call"]
    elif action == "raise":
        if type(target) is not int or not choices["raise"]:
            raise Conflict("raise_not_allowed")
        if target <= hand["current_bet"] or target > choices["max_raise_to"]:
            raise Conflict("raise_out_of_range")
        if target < choices["min_raise_to"] and target != choices["max_raise_to"]:
            raise Conflict("raise_below_minimum")
        delta = target - hand["current_bet"]
        if delta >= hand["increment"]:
            hand["increment"] = delta
        hand["current_bet"] = target
        chips = target - p["bet"]
    else:
        raise Conflict("unknown_action")
    contribute(p, chips)
    p["acted_at"], p["reopen"] = hand["current_bet"], hand["increment"]
    hand["history"].append(
        {
            "seat": actor,
            "street": hand["street"],
            "action": action,
            "amount": chips,
            "raise_to": p["bet"],
            "all_in": p["stack"] == 0,
            "automatic": automatic,
        }
    )
    advance(hand, actor)


def advance(hand, after):
    alive = [p for p in hand["players"] if not p["folded"]]
    if len(alive) == 1:
        finish(hand)
        return
    able = [p for p in alive if p["stack"] > 0]
    if len(able) == 1:
        hand["current_bet"] = max(p["bet"] for p in alive)
    for i in clockwise(hand, after):
        p = hand["players"][i]
        if p["folded"] or not p["stack"]:
            continue
        if p["bet"] < hand["current_bet"] or (p["acted_at"] is None and len(able) > 1):
            hand["actor"] = i
            hand["turn"] += 1
            return
    if hand["street"] == "river":
        finish(hand)
        return
    hand["street"] = STREETS[STREETS.index(hand["street"]) + 1]
    hand["deck"].pop()  # Burn before every public street.
    for _ in range(3 if hand["street"] == "flop" else 1):
        hand["board"].append(hand["deck"].pop())
    hand["current_bet"], hand["increment"] = 0, 100
    for p in hand["players"]:
        p["bet"], p["acted_at"], p["reopen"] = 0, None, 100
    advance(hand, hand["button"])


def finish(hand):
    players = hand["players"]
    live = [i for i, p in enumerate(players) if not p["folded"]]
    payouts = {p["id"]: 0 for p in players}
    refunds = {p["id"]: 0 for p in players}
    hand["showdown"] = len(live) > 1
    scores = (
        {i: strength(players[i]["cards"] + hand["board"]) for i in live}
        if len(live) > 1
        else {}
    )
    floor = 0
    pots = []
    for level in sorted({p["paid"] for p in players if p["paid"]}):
        contributors = [i for i, p in enumerate(players) if p["paid"] >= level]
        chips = (level - floor) * len(contributors)
        floor = level
        if len(contributors) == 1:
            user = players[contributors[0]]["id"]
            payouts[user] += chips
            refunds[user] += chips
            continue
        eligible = [i for i in contributors if i in live]
        if len(live) == 1:
            winners = live
        else:
            if not eligible:
                raise Conflict("pot_without_eligible_player")
            best = max(scores[i] for i in eligible)
            winners = [i for i in eligible if scores[i] == best]
        ordered = [i for i in clockwise(hand, hand["button"]) if i in winners]
        share, odd = divmod(chips, len(winners))
        for offset, i in enumerate(ordered):
            payouts[players[i]["id"]] += share + (offset < odd)
        pots.append({"amount": chips, "winners": [players[i]["id"] for i in ordered]})
    if sum(payouts.values()) != sum(p["paid"] for p in players):
        raise Conflict("payout_not_conserved")
    hand.update(payouts=payouts, refunds=refunds, pots=pots, actor=None)


def project(hand, user):
    if hand is None:
        return None
    players = []
    for p in hand["players"]:
        shown = p["id"] == user or (hand["showdown"] and not p["folded"])
        players.append(
            {
                "id": p["id"],
                "stack": str(p["stack"]),
                "bet": str(p["bet"]),
                "paid": str(p["paid"]),
                "folded": p["folded"],
                "cards": p["cards"] if shown else [],
            }
        )
    return {
        "id": hand["id"],
        "players": players,
        "button": hand["button"],
        "board": hand["board"],
        "street": hand["street"],
        "actor": hand["actor"],
        "turn": hand["turn"],
        "pot": str(sum(p["paid"] for p in hand["players"])),
        "legal": {k: str(v) if type(v) is int else v for k, v in legal(hand).items()}
        if hand["actor"] is not None and hand["players"][hand["actor"]]["id"] == user
        else {},
        "payouts": {k: str(v) for k, v in hand["payouts"].items()}
        if hand["payouts"] is not None
        else None,
        "deadline": hand.get("deadline"),
        "extensions": hand.get("extensions", 0),
    }
