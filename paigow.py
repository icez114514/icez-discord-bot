"""Pai Gow with a fully wild Joker (52) and versioned hand rules."""

from collections import Counter
from dataclasses import dataclass

JOKER = 52
LEGACY_RULE_VERSION = 'wild-house-v1'
RULE_VERSION = 'wild-house-v2'
NAMES = ('高牌', '對子', '兩對', '三條', '順子', '同花', '葫蘆', '四條', '同花順', '五條')


@dataclass(frozen=True)
class Evaluation:
    score: tuple[int, ...]
    joker_as: int | None = None

    @property
    def name(self):
        return NAMES[self.score[0]]


def rank(card):
    return 14 if card % 13 == 0 else card % 13 + 1


def _score(cards, rules=RULE_VERSION):
    values = sorted(map(rank, cards), reverse=True)
    groups = sorted(((count, value) for value, count in Counter(values).items()), reverse=True)
    if len(cards) == 2:
        return (1, values[0]) if values[0] == values[1] else (0, *values)
    flush = len({c // 13 for c in cards}) == 1
    straight = 0
    if len(groups) == 5:
        if values == [14, 5, 4, 3, 2]:
            straight = 14 if rules == LEGACY_RULE_VERSION else 5
        elif values[0] - values[-1] == 4:
            straight = 15 if rules == LEGACY_RULE_VERSION and values[0] == 14 else values[0]
    counts = [g[0] for g in groups]
    ranks = tuple(g[1] for g in groups)
    if counts == [5]:
        return (9, *ranks)
    if straight and flush:
        return (8, straight)
    if counts == [4, 1]:
        return (7, *ranks)
    if counts == [3, 2]:
        return (6, *ranks)
    if flush:
        return (5, *values)
    if straight:
        return (4, straight)
    return ({3: 3, 2: 2 if counts[:2] == [2, 2] else 1}.get(counts[0], 0), *ranks)


def evaluate(cards, *, rules=RULE_VERSION) -> Evaluation:
    if (len(cards) not in (2, 5) or any(type(c) is not int or not 0 <= c <= JOKER for c in cards)
            or len(set(cards)) != len(cards)):
        raise ValueError('Expected two or five distinct physical cards')
    if JOKER not in cards:
        return Evaluation(_score(cards, rules))
    natural = [c for c in cards if c != JOKER]
    # Duplicate represented cards are intentional: a Joker can make five of a kind.
    candidates = [Evaluation(_score(natural + [c], rules), c) for c in range(52)]
    return max(candidates, key=lambda e: e.score)


def split(hand, front):
    if (len(hand) != 7 or len(set(hand)) != 7 or len(front) != 2
            or len(set(front)) != 2 or any(type(c) is not int for c in front)
            or not set(front).issubset(hand)):
        raise ValueError('Select exactly two cards from your seven cards')
    return list(front), [c for c in hand if c not in front]


def legal_split(hand, front, *, rules=RULE_VERSION):
    try:
        low, high = split(hand, front)
        # Tuple comparison deliberately compares common ranks first, then length:
        # remaining back-hand kickers outrank an otherwise equal two-card hand.
        return evaluate(high, rules=rules).score > evaluate(low, rules=rules).score
    except (ValueError, TypeError):
        return False


def house_way(hand, *, rules=RULE_VERSION):
    """MotorCity-inspired grouping, evaluated under the selected rule version.

    Match the first applicable row below. Within a row maximize front, then back;
    equal ranks choose the lexicographically smallest physical front-card IDs.
    Impossible rows fall back to strongest legal back, then front.
    """
    from itertools import combinations
    if (len(hand) != 7 or len(set(hand)) != 7
            or any(type(c) is not int or not 0 <= c <= JOKER for c in hand)):
        raise ValueError('Expected seven distinct cards')
    hand = sorted(hand)
    choices = []
    for front in combinations(hand, 2):
        low, high = split(hand, front)
        a, b = evaluate(low, rules=rules).score, evaluate(high, rules=rules).score
        if b > a:
            choices.append((list(front), a, b))
    counts = Counter(rank(c) for c in hand if c != JOKER)
    if JOKER in hand:
        # Grouping classification only. Every actual candidate still evaluates
        # its Joker freely, including straights/flushes of a different rank.
        wild_rank = max(counts, key=lambda r: (counts[r], r))
        counts[wild_rank] += 1
    groups = sorted(((n, r) for r, n in counts.items()), reverse=True)
    pairs = sorted((r for r, n in counts.items() if n >= 2), reverse=True)
    top_count, top_rank = groups[0]
    preferred = []
    if top_count == 5:
        # Keep five with a spare natural pair; otherwise put a pair in front.
        preferred = [c for c in choices if c[2][0] == 9 and c[1][0] == 1]
        if not preferred:
            preferred = [c for c in choices if c[1] == (1, top_rank) and c[2][0] >= 3]
    elif top_count == 4:
        other_pairs = [r for r in pairs if r != top_rank]
        if other_pairs:
            preferred = [c for c in choices if c[2][0] == 7 and c[1][0] == 1]
        elif top_rank <= 6:
            preferred = [c for c in choices if c[2][0] == 7]
        else:
            if top_rank <= 10:
                preferred = [c for c in choices if c[2][0] == 7 and c[1][:2] == (0, 14)]
            if not preferred:
                preferred = [c for c in choices if c[1] == (1, top_rank) and c[2][0] == 1]
    elif top_count == 3 and len(pairs) >= 2:
        # Full house/two triples: strongest available pair in front, trips behind.
        preferred = [c for c in choices if c[1][0] == 1 and c[2][0] in (3, 6)]
    elif len(pairs) >= 3:
        preferred = [c for c in choices if c[1] == (1, pairs[0])]
    elif len(pairs) == 2:
        high, low = pairs
        must_split = low >= 11 or (7 <= low <= 10 and high >= 11)
        if not must_split:
            preferred = [c for c in choices if c[2][0] == 2 and c[1][:2] == (0, 14)]
        if not preferred:
            preferred = [c for c in choices if c[1] == (1, low) and c[2][:2] == (1, high)]
    else:
        # Preserve a straight/flush/straight flush, preferring a front pair.
        preferred = [c for c in choices if c[2][0] in (4, 5, 8)]
        if not preferred and top_count == 3:
            if top_rank == 14:
                preferred = [c for c in choices if c[2][:2] == (1, 14) and c[1][:2] == (0, 14)]
            else:
                preferred = [c for c in choices if c[2][0] == 3]
        elif not preferred and top_count == 2:
            preferred = [c for c in choices if c[2][0] == 1]
        elif not preferred:
            ordered = sorted(hand, key=lambda c: (-rank(c), c))
            wanted = set(ordered[1:3])
            preferred = [c for c in choices if set(c[0]) == wanted]
    if preferred:
        return max(preferred, key=lambda c: (c[1], c[2], tuple(-v for v in c[0])))[0]
    return max(choices, key=lambda c: (c[2], c[1], tuple(-v for v in c[0])))[0]


def shuffled_deck():
    import secrets
    cards = list(range(53))
    secrets.SystemRandom().shuffle(cards)
    return cards


def deal(cards):
    if len(cards) != 53 or any(type(c) is not int for c in cards) or set(cards) != set(range(53)):
        raise ValueError('Expected one complete 53-card deck')
    player, dealer = cards[:14:2], cards[1:14:2]
    return {'rules': RULE_VERSION, 'deck': cards[14:], 'player': player, 'dealer': dealer,
            'front': [], 'dealer_front': house_way(dealer), 'suggested_front': house_way(player),
            'confirmed': False}


def validate(state):
    if not isinstance(state, dict) or state.get('rules') not in (RULE_VERSION, LEGACY_RULE_VERSION):
        raise ValueError('Invalid Pai Gow rule version')
    for key in ('deck', 'player', 'dealer', 'front', 'dealer_front', 'suggested_front'):
        if not isinstance(state.get(key), list):
            raise ValueError('Invalid persisted Pai Gow cards')
    cards = state['deck'] + state['player'] + state['dealer']
    if (len(cards) != 53 or any(type(c) is not int for c in cards) or set(cards) != set(range(53))
            or len(state['player']) != 7 or len(state['dealer']) != 7
            or type(state.get('confirmed')) is not bool
            or not legal_split(state['dealer'], state['dealer_front'], rules=state['rules'])
            or not legal_split(state['player'], state['suggested_front'], rules=state['rules'])
            or (state['front'] and not legal_split(state['player'], state['front'], rules=state['rules']))
            or (state['confirmed'] and not state['front'])):
        raise ValueError('Invalid persisted Pai Gow')


def act(state, action, front=None):
    from casino_rules import CasinoError
    if action == 'auto':
        state['front'] = list(state['suggested_front'])
    elif action == 'select':
        if not legal_split(state['player'], front, rules=state['rules']):
            raise CasinoError('請選擇兩張前墩牌，且後墩必須強於前墩；請重新選牌。')
        state['front'] = list(front)
    elif action == 'confirm':
        if not state['front']:
            raise CasinoError('請先選擇前墩兩張牌，或使用自動分牌。')
        state['confirmed'] = True
    else:
        raise CasinoError('無效的牌局操作。')


def compare(player_front, player_back, dealer_front, dealer_back, *, rules=RULE_VERSION):
    """Return each raw comparison (-1/0/1) and the bankroll outcome."""
    comparisons = []
    for player, dealer in ((player_front, dealer_front), (player_back, dealer_back)):
        a, b = evaluate(player, rules=rules).score, evaluate(dealer, rules=rules).score
        comparisons.append((a > b) - (a < b))
    if rules == LEGACY_RULE_VERSION:
        wins = sum(value > 0 for value in comparisons)
        return tuple(comparisons), ('loss', 'tie', 'win')[wins]
    total = sum(comparisons)
    return tuple(comparisons), 'win' if total > 0 else 'loss' if total < 0 else 'tie'


def result(state):
    if not state['confirmed']:
        return None
    return compare(*split(state['player'], state['front']),
                   *split(state['dealer'], state['dealer_front']), rules=state['rules'])[1]


def display_order(cards, *, joker_as=None):
    """Return physical IDs in A-K order, optionally positioning a resolved Joker."""
    def key(card):
        represented = joker_as if card == JOKER and joker_as is not None else card
        if represented == JOKER:
            return (13, 0, True)
        # A natural card precedes a Joker representing the exact same card.
        return (represented % 13, represented // 13, card == JOKER)
    return sorted(cards, key=key)
