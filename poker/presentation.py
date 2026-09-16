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


def publish_hand(table, now):
    hand = table["hand"]
    events = hand.get("presentation", [])
    for event in events[hand.get("published", 0) :]:
        emit(table, now, **event)
    hand["published"] = len(events)
