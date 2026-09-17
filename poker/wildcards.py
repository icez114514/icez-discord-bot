"""Best legal five-card hand; jokers never consult another player's cards."""
from collections import Counter

RANKS = "23456789TJQKA"
CARDS = tuple(r + s for r in RANKS for s in "cdhs")
JOKERS = ("Xr", "Xb")


def deck_for(mode="standard"):
    if mode not in ("standard", "double_joker"):
        raise ValueError("invalid_game_mode")
    return CARDS + (JOKERS if mode == "double_joker" else ())


def evaluate(cards, details=False):
    """Category-first search, bounded by ranks, not 52**joker_count."""
    ordinary = [c for c in cards if c not in JOKERS]
    jokers = [c for c in cards if c in JOKERS]
    counts = Counter(RANKS.index(c[0]) + 2 for c in ordinary)
    n = len(jokers)
    ranks = list(range(14, 1, -1))

    def result(category, target, suit=None):
        score = (category, *target)
        if not details:
            return score
        available = ordinary[:]
        originals, substitutions, selected = [], {}, []
        missing = []
        for r in target:
            card = next((c for c in available if RANKS.index(c[0])+2 == r and (suit is None or c[1] == suit)), None)
            if card:
                available.remove(card)
                originals.append(card)
                selected.append(card)
            else:
                missing.append(r)
        for joker, r in zip(jokers, missing):
            card = next(RANKS[r-2]+s for s in (suit or "cdhs") if RANKS[r-2]+s not in selected)
            originals.append(joker)
            selected.append(card)
            substitutions[joker] = card
        return {"score": score, "cards": originals, "substitutions": substitutions}

    def finish(category, target, keys, suit=None):
        score = (category, *keys)
        if details:
            value = result(category, target, suit)
            value["score"] = score
            return value
        return score

    def straight(suit=None):
        present = {RANKS.index(c[0])+2 for c in ordinary if suit is None or c[1] == suit}
        for high in range(14, 4, -1):
            target = list(range(high, high-5, -1)) if high > 5 else [5,4,3,2,14]
            if sum(r not in present for r in target) <= n:
                return high, target

    straights = [(s, straight(s)) for s in "cdhs"]
    valid = [(s,v) for s,v in straights if v]
    if valid:
        suit, (high,target) = max(valid, key=lambda x:x[1][0])
        return finish(8,target,[high],suit)

    def groups(required):
        cost = sum(max(0,num-counts[r]) for r,num in required)
        if cost > n:
            return None
        target = [r for r,num in required for _ in range(num)]
        if len(target) == 5:
            return target
        excluded = {r for r,_ in required}
        left = n-cost
        for r in ranks:
            if r in excluded:
                continue
            if counts[r] or left:
                target.append(r)
                if not counts[r]:
                    left -= 1
                if len(target) == 5:
                    return target
        return target if len(target) == 5 else None

    for r in ranks:
        if counts[r]+n < 4:
            continue
        target = groups([(r,4)])
        if target:
            return finish(7,target,[r,target[-1]])
    for r in ranks:
        if counts[r]+n < 3:
            continue
        for p in ranks:
            if p != r and counts[p]+n >= 2:
                target = groups([(r,3),(p,2)])
                if target:
                    return finish(6,target,[r,p])
    flushes=[]
    for suit in "cdhs":
        present = {RANKS.index(c[0])+2 for c in ordinary if c[1] == suit}
        if len(present)+n >= 5:
            left=n
            target=[]
            for r in ranks:
                if r in present or left:
                    target.append(r)
                    if r not in present:
                        left-=1
                    if len(target)==5:
                        break
            flushes.append((target,suit))
    if flushes:
        target,suit=max(flushes)
        return finish(5,target,target,suit)
    run=straight()
    if run:
        return finish(4,run[1],[run[0]])
    for r in ranks:
        if counts[r]+n < 3:
            continue
        target=groups([(r,3)])
        if target:
            return finish(3,target,[r,*target[3:]])
    for r in ranks:
        if counts[r]+n < 2:
            continue
        for p in ranks:
            if p < r and counts[p]+n >= 2:
                target=groups([(r,2),(p,2)])
                if target:
                    return finish(2,target,[r,p,target[-1]])
    for r in ranks:
        target=groups([(r,2)])
        if target:
            return finish(1,target,[r,*target[2:]])
    target=groups([])
    if target is None:
        raise ValueError("five_cards_required")
    return finish(0,target,target)
