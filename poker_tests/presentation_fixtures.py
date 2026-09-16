"""Deterministic public recordings for browser presentation acceptance only."""

import copy
import json
import time
from unittest.mock import patch

from poker import rules
from poker.presentation import publish_hand, emit

A, B, C, D = (
    "111111111111111111",
    "222222222222222222",
    "333333333333333333",
    "444444444444444444",
)


def recordings(sweep=False):
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
            list(
                zip(
                    (A, B, C, D),
                    (501, 301, 201, 101) if sweep else (101, 201, 301, 501),
                )
            ),
            0,
            "browser-hand",
        )
    now = time.time()
    table = {"id": "main", "hand": hand}
    members = [
        {
            "id": p["id"],
            "seat": i,
            "mode": "active",
            "connected": True,
            "sitout": False,
            "expires": None,
            "stack": str(p["start"]),
            "leaving": False,
            "topup": None,
            "notice": None,
            "npc_failures": 0,
        }
        for i, p in enumerate(hand["players"])
    ]
    snapshots = [
        {
            "id": "main",
            "name": "公開事件驗收",
            "version": 0,
            "joined": True,
            "control": True,
            "owner": A,
            "closed": False,
            "members": members,
            "hand": None,
            "event_seq": 0,
            "events": [],
            "time_bank": 60,
            "server_time": now,
        }
    ]

    def capture():
        publish_hand(table, now)
        hand.update(deadline=now + 20, extensions=0)
        if hand["actor"] is not None:
            emit(
                table,
                now,
                "turn",
                hand_id=hand["id"],
                user=hand["players"][hand["actor"]]["id"],
                turn=hand["turn"],
            )
        state = copy.deepcopy(snapshots[0])
        state.update(
            version=len(snapshots),
            hand=rules.project(hand, A),
            events=copy.deepcopy(table["events"]),
            event_seq=table["event_seq"],
        )
        for m, p in zip(state["members"], hand["players"]):
            m["stack"] = str(p["stack"] + (hand["payouts"] or {}).get(p["id"], 0))
        snapshots.append(copy.deepcopy(state))

    capture()
    for user in (D, A, B, C):
        rules.act(hand, user, "all_in")
        capture()
    return snapshots


if __name__ == "__main__":
    import sys

    print(json.dumps(recordings("--sweep" in sys.argv), ensure_ascii=True))
