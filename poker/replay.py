"""Participant-only replay of versioned, durable settlement evidence."""

import copy
import json

from fastapi import HTTPException, Query, Request

from . import rules
from .sessions import authenticate

POLICY = {
    "version": 1,
    "support": "僅支援回放版本 1 起、從發牌到結算事件完整的新手牌；舊格式或缺失資料不補造。",
    "retention": "沿用既有保存政策，不新增自動刪除；帳務與稽核紀錄保留。",
    "page_size": 20,
}


def frames(hand, user):
    """Validate public events against settlement before exposing any frames."""
    events = hand["presentation"]
    if hand.get("replay_version") != 1 or hand.get("void"):
        raise ValueError("unsupported")
    if events[0]["kind"] != "deal" or events[-1]["kind"] != "complete":
        raise ValueError("incomplete")
    players = {
        p["id"]: {
            "id": p["id"],
            "stack": str(p["start"]),
            "bet": "0",
            "paid": "0",
            "folded": False,
            "cards": p["cards"] if p["id"] == user else [],
        }
        for p in hand["players"]
    }
    board = []
    output = []
    received = {u: 0 for u in players}
    refunds = {u: 0 for u in players}
    awards: dict[tuple[str, str], int] = {}
    actions = []
    revealed = False
    street = "preflop"
    settlement = rules.project(hand, user)["settlement"]
    for index, event in enumerate(events):
        kind = event["kind"]
        if event["hand_id"] != hand["id"]:
            raise ValueError("wrong_hand")
        public = {
            k: event[k]
            for k in (
                "kind",
                "street",
                "user",
                "action",
                "amount",
                "raise_to",
                "all_in",
                "automatic",
            )
            if k in event
        }
        if kind == "deal":
            if index != 0:
                raise ValueError("duplicate_deal")
        elif kind == "action":
            p = players[event["user"]]
            amount = int(event["amount"])
            if amount < 0 or int(p["stack"]) < amount or p["folded"] or revealed:
                raise ValueError("invalid_action")
            p["stack"] = str(int(p["stack"]) - amount)
            p["bet"] = str(int(p["bet"]) + amount)
            p["paid"] = str(int(p["paid"]) + amount)
            p["folded"] = event["action"] == "fold"
            actions.append(
                (
                    event["user"],
                    street,
                    "raise" if event["action"] == "bet" else event["action"],
                    amount,
                )
            )
        elif kind == "collect":
            if event["amounts"] != {
                u: p["bet"] for u, p in players.items() if int(p["bet"])
            }:
                raise ValueError("invalid_collection")
            for p in players.values():
                p["bet"] = "0"
        elif kind == "board":
            next_street = rules.STREETS[rules.STREETS.index(street) + 1]
            if (
                event["street"] != next_street
                or event["board"]
                != hand["board"][: {"flop": 3, "turn": 4, "river": 5}[next_street]]
            ):
                raise ValueError("invalid_board")
            street, board = next_street, event["board"]
        elif kind == "showdown":
            if revealed or not hand["showdown"] or len(board) != 5:
                raise ValueError("invalid_showdown")
            revealed = True
            for p in hand["players"]:
                if not p["folded"]:
                    players[p["id"]]["cards"] = p["cards"]
        elif kind in ("payout", "refund"):
            if hand["showdown"] and not revealed:
                raise ValueError("early_award")
            u, amount = event["user"], int(event["amount"])
            if amount <= 0:
                raise ValueError("invalid_award")
            received[u] += amount
            players[u]["stack"] = str(int(players[u]["stack"]) + amount)
            if kind == "refund":
                refunds[u] += amount
            else:
                key = (event["pot_id"], u)
                awards[key] = awards.get(key, 0) + amount
        elif kind == "complete":
            if index != len(events) - 1:
                raise ValueError("early_completion")
        else:
            raise ValueError("unknown_event")
        if event["street"] != street:
            raise ValueError("wrong_street")
        output.append(
            {
                "step": index,
                "event": public,
                "street": street,
                "board": list(board),
                "players": copy.deepcopy(list(players.values())),
                "pot": str(
                    sum(int(p["paid"]) for p in players.values())
                    - sum(received.values())
                ),
                "settlement": settlement if kind == "complete" else None,
            }
        )
    expected_actions = [
        (hand["players"][a["seat"]]["id"], a["street"], a["action"], a["amount"])
        for a in hand["history"]
    ]
    expected_awards = {
        (p["id"], u): int(a)
        for p in settlement["pots"]
        for u, a in p["awards"].items()
        if int(a)
    }
    if (
        actions != expected_actions
        or board != hand["board"]
        or revealed != hand["showdown"]
        or received != hand["payouts"]
        or refunds != hand["refunds"]
        or awards != expected_awards
    ):
        raise ValueError("inconsistent_history")
    for p in hand["players"]:
        actual = players[p["id"]]
        if (
            int(actual["paid"]) != p["paid"]
            or actual["folded"] != p["folded"]
            or int(actual["stack"]) != p["stack"] + received[p["id"]]
        ):
            raise ValueError("inconsistent_player")
    return output


def detail(db, user, hand_id):
    row = db.execute(
        "SELECT h.status,h.table_id,e.event FROM hands h "
        "JOIN participants p USING(hand_id) "
        "LEFT JOIN settlements s USING(hand_id) "
        "LEFT JOIN hand_events e ON e.command_id=s.command_id "
        "WHERE h.hand_id=? AND p.user_id=? AND h.status!='active'",
        (hand_id, user),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "hand_unavailable")
    result = {
        "hand_id": hand_id,
        "table_id": row["table_id"],
        "policy": POLICY,
        "complete": False,
        "frames": [],
        "reason": "資料不完整、舊格式或作廢手牌；無法完整回放。",
    }
    try:
        evidence = json.loads(row["event"])
        hand = evidence["data"]["snapshot"]
        contributions = {
            p["user_id"]: p["contribution"]
            for p in db.execute(
                "SELECT user_id,contribution FROM participants WHERE hand_id=?",
                (hand_id,),
            )
        }
        if (
            row["status"] != "settled"
            or evidence["kind"] != "settle"
            or hand["id"] != hand_id
            or {p["id"]: p["paid"] for p in hand["players"]} != contributions
            or {u: str(n) for u, n in hand["payouts"].items()}
            != evidence["data"]["payouts"]
        ):
            return result
        result.update(frames=frames(hand, user), complete=True, reason=None)
    except (KeyError, ValueError, TypeError, IndexError):
        pass
    return result


def install(app, cookie):
    @app.get("/api/hands")
    async def history(
        request: Request,
        before: int | None = Query(default=None, ge=1),
        limit: int = Query(default=20, ge=1, le=50),
    ):
        def read(db):
            user = authenticate(db, request.cookies.get(cookie, ""))
            rows = db.execute(
                "SELECT h.hand_id,h.table_id,h.status,h.rowid AS cursor FROM hands h "
                "JOIN participants p USING(hand_id) WHERE p.user_id=? AND h.status!='active' "
                "AND (? IS NULL OR h.rowid<?) ORDER BY h.rowid DESC LIMIT ?",
                (user, before, before, limit + 1),
            ).fetchall()
            return {
                "hands": [dict(r) for r in rows[:limit]],
                "policy": POLICY,
                "next_cursor": rows[limit - 1]["cursor"] if len(rows) > limit else None,
            }

        return await app.state.store.run(read)

    @app.get("/api/hands/{hand_id}")
    async def hand(request: Request, hand_id: str):
        def read(db):
            user = authenticate(db, request.cookies.get(cookie, ""))
            return detail(db, user, hand_id)

        return await app.state.store.run(read)
