"""Versioned completed-hand projections shared by HTTP and Discord."""

import json
import time
from datetime import datetime

from . import rules
from .money import TAIPEI
from .store import Conflict

VERSION = 1
METRICS = ("net_win", "vpip", "pfr", "three_bet", "fold_three_bet", "cbet", "wsd")


def calculate(hand):
    """Replay public actions and engine raise rights; never deal random cards.

    The completed snapshot supplies showdown participation and payouts (including
    uncalled refunds). Cards are not exposed by the projection.
    """
    players = hand.get("players", [])
    if not players or any(len(p.get("cards", [])) != 2 for p in players):
        return {}
    counts = {p["id"]: {m: [0, 0] for m in METRICS} for p in players}
    replay = {
        "players": [
            dict(
                p,
                stack=p["start"],
                bet=0,
                paid=0,
                folded=False,
                acted_at=None,
                reopen=100,
            )
            for p in players
        ],
        "actor": None,
        "payouts": None,
        "current_bet": 100,
        "increment": 100,
    }
    raises, last_raiser, street = 0, None, "preflop"
    flop_seen = set()
    for event in hand["history"]:
        if event["street"] != street:
            street = event["street"]
            replay["current_bet"], replay["increment"] = 0, 100
            for p in replay["players"]:
                p.update(bet=0, acted_at=None, reopen=100)
        seat = event["seat"]
        p = replay["players"][seat]
        user, action, chips = p["id"], event["action"], event["amount"]
        metric = counts[user]
        replay["actor"] = seat
        blind = action in ("small_blind", "big_blind")
        if not blind:
            live = [q for q in replay["players"] if not q["folded"]]
            if sum(q["stack"] > 0 for q in live) == 1:
                replay["current_bet"] = max(q["bet"] for q in live)
            legal = rules.legal(replay)
            if street == "preflop":
                if raises == 1 and legal["raise"]:
                    metric["three_bet"][1] = 1
                    if action == "raise":
                        metric["three_bet"][0] = 1
                if raises == 2 and legal["call"] > 0:
                    metric["fold_three_bet"][1] = 1
                    if action == "fold":
                        metric["fold_three_bet"][0] = 1
                if chips > 0 and action in ("call", "raise"):
                    metric["vpip"][0] = 1
                if action == "raise":
                    metric["pfr"][0] = 1
                    raises += 1
                    last_raiser = user
            elif street == "flop" and user not in flop_seen:
                flop_seen.add(user)
                if (
                    user == last_raiser
                    and replay["current_bet"] == 0
                    and legal["raise"]
                ):
                    metric["cbet"] = [int(action == "raise"), 1]
            if action == "raise":
                target = p["bet"] + chips
                delta = target - replay["current_bet"]
                if delta >= replay["increment"]:
                    replay["increment"] = delta
                replay["current_bet"] = target
            p["acted_at"], p["reopen"] = replay["current_bet"], replay["increment"]
            p["folded"] = action == "fold"
        rules.contribute(p, chips)
    for p in players:
        user = p["id"]
        metric = counts[user]
        net = hand["payouts"].get(user, 0) - p["paid"]
        metric["net_win"] = [int(net > 0), 1]
        metric["vpip"][1] = metric["pfr"][1] = 1
        showdown = bool(hand["showdown"] and not p["folded"])
        prize = hand["payouts"].get(user, 0) - hand["refunds"].get(user, 0)
        metric["wsd"] = [int(showdown and prize > 0), int(showdown)]
    return counts


def persist(db, hand_id, hand, now):
    counts = calculate(hand)
    classification = (
        "mixed"
        if any(p["id"].startswith("npc:") for p in hand.get("players", []))
        else "human"
    )
    for p in hand.get("players", []):
        user = p["id"]
        if user.startswith("npc:") or user not in counts:
            continue
        db.execute(
            "INSERT INTO hand_statistics VALUES(?,?,?,?,?,?,?)",
            (
                hand_id,
                user,
                hand.get("settled_at", now),
                classification,
                VERSION,
                hand["payouts"].get(user, 0) - p["paid"],
                json.dumps(counts[user]),
            ),
        )


def metric_view(numerator, denominator, threshold):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": f"{100 * numerator / denominator:.1f}%" if denominator else "—",
        "low_sample": denominator < threshold,
    }


def query(db, user, period="all", opponents="all", now=None):
    if period not in ("all", "30", "7") or opponents not in ("all", "human", "mixed"):
        raise Conflict("invalid_statistics_filter")
    end = time.time() if now is None else now
    start = end - int(period) * 86400 if period != "all" else None
    totals = {}
    for row in db.execute(
        "SELECT user_id,counts FROM hand_statistics WHERE settled_at<? "
        "AND (? IS NULL OR settled_at>=?) AND (?='all' OR classification=?)",
        (end, start, start, opponents, opponents),
    ):
        total = totals.setdefault(row["user_id"], {m: [0, 0] for m in METRICS})
        for key, (n, d) in json.loads(row["counts"]).items():
            total[key][0] += n
            total[key][1] += d

    def summary(uid, private=False):
        total = totals.get(uid, {m: [0, 0] for m in METRICS})
        metrics = {
            m: metric_view(*total[m], 100 if m in ("net_win", "vpip", "pfr") else 20)
            for m in METRICS
            if private or m == "net_win"
        }
        return {
            "hands": total["net_win"][1],
            "low_sample": total["net_win"][1] < 100,
            "metrics": metrics,
        }

    leaderboard, rank, previous = [], 0, None
    for i, row in enumerate(
        db.execute(
            "SELECT user_id,settled FROM accounts WHERE user_id NOT LIKE 'npc:%' ORDER BY settled DESC,user_id"
        ),
        1,
    ):
        if row["settled"] != previous:
            rank = i
        previous = row["settled"]
        leaderboard.append(
            {
                "rank": rank,
                "user_id": row["user_id"],
                "settled": str(row["settled"]),
                **summary(row["user_id"]),
            }
        )
    return {
        "period": period,
        "opponents": opponents,
        "formula_version": VERSION,
        "as_of": datetime.fromtimestamp(end, TAIPEI).isoformat(),
        "start": datetime.fromtimestamp(start, TAIPEI).isoformat()
        if start is not None
        else None,
        "timezone": "Asia/Taipei",
        "leaderboard": leaderboard,
        "personal": {"user_id": user, **summary(user, True)},
    }
