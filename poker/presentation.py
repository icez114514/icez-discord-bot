"""Explicit public presentation records; never serialize a private hand into an event."""


def hand_event(hand, kind, **data):
    hand.setdefault("presentation", []).append(
        {"kind": kind, "hand_id": hand["id"], "street": hand["street"], **data}
    )


def collect(hand):
    amounts = {p["id"]: str(p["bet"]) for p in hand["players"] if p["bet"]}
    if amounts:
        hand_event(hand, "collect", amounts=amounts)


def emit(table, now, kind, **data):
    seq = table.get("event_seq", 0) + 1
    table["event_seq"] = seq
    event = {"id": f"{table['id']}:{seq}", "seq": seq, "at": now, "kind": kind, **data}
    table["events"] = [*table.get("events", []), event][-256:]


RESULT_HOLD_SECONDS = 4.4


def event_duration(event, players, all_in_runout=False):
    return {"deal": players * 140 + 420, "action": 120, "collect": 220,
            "all_in_reveal": 700, "board": 2000 if all_in_runout else 650,
            "showdown": 650, "payout": 320, "refund": 320,
            "complete": 0}.get(event["kind"], 0) / 1000


def next_hand_delay(table, now):
    # Admission countdown also gives the result its full hold after queued awards.
    minimum = 5.5 if table.get("last") else 5
    return max(now + minimum, table.get("presentation_end", now) + RESULT_HOLD_SECONDS + 0.5)


def publish_hand(table, now, db=None):
    hand = table["hand"]
    events = hand.get("presentation", [])
    published = hand.get("published", 0)
    runout = any(e["kind"] == "all_in_reveal" for e in events[:published])
    for event in events[published:]:
        runout = runout or event["kind"] == "all_in_reveal"
        table["presentation_end"] = max(now, table.get("presentation_end", now)) + event_duration(event, len(hand["players"]), runout)
        data = dict(event)
        if db is not None and event.get("user") and event["kind"] == "action":
            from .voices import voice_for
            actor = next((m for m in table["members"] if m["id"] == event["user"]), None)
            if actor:
                data["voice_pack"] = voice_for(db, actor)
        emit(table, now, **data)
    hand["published"] = len(events)
