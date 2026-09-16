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


def publish_hand(table, now, db=None):
    hand = table["hand"]
    events = hand.get("presentation", [])
    for event in events[hand.get("published", 0) :]:
        data = dict(event)
        if db is not None and event.get("user") and event["kind"] == "action":
            from .voices import voice_for
            actor = next((m for m in table["members"] if m["id"] == event["user"]), None)
            if actor:
                data["voice_pack"] = voice_for(db, actor)
        emit(table, now, **data)
    hand["published"] = len(events)
