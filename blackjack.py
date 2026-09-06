"""Single-deck blackjack. Card IDs are suit * 13 + rank (ace = 0)."""

import secrets


def shuffled_deck():
    cards = list(range(52))
    secrets.SystemRandom().shuffle(cards)
    return cards


def total(cards):
    value = sum(min(card % 13 + 1, 10) for card in cards)
    return value + 10 if any(card % 13 == 0 for card in cards) and value <= 11 else value


def natural(cards):
    return len(cards) == 2 and total(cards) == 21


def deal(cards):
    if len(cards) != 52 or any(type(c) is not int for c in cards) or set(cards) != set(range(52)):
        raise ValueError('Expected one complete deck')
    return {'deck': cards[4:], 'player': [cards[0], cards[2]],
            'dealer': [cards[1], cards[3]], 'actions': [], 'standing': False}


def validate(state):
    cards = state['deck'] + state['player'] + state['dealer']
    if (len(cards) != 52 or any(type(c) is not int for c in cards)
            or set(cards) != set(range(52)) or len(state['player']) < 2
            or len(state['dealer']) < 2 or type(state['standing']) is not bool
            or not isinstance(state['actions'], list)):
        raise ValueError('Invalid persisted blackjack')


def result(state):
    player, dealer = state['player'], state['dealer']
    if natural(player) or natural(dealer):
        return 'tie' if natural(player) and natural(dealer) else 'win' if natural(player) else 'loss'
    if total(player) > 21:
        return 'loss'
    if not state['standing']:
        return None
    while total(dealer) < 17:
        dealer.append(state['deck'].pop(0))
    left, right = total(player), total(dealer)
    return 'win' if right > 21 or left > right else 'tie' if left == right else 'loss'


def act(state, action):
    if action in ('hit', 'double'):
        state['player'].append(state['deck'].pop(0))
    state['standing'] = action in ('stand', 'double') or total(state['player']) >= 21
    state['actions'].append(action)
