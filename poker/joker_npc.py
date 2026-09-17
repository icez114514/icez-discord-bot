"""Public-observation-only strategy for the 54-card game, run in the NPC worker."""
import random
import time
from .wildcards import deck_for, evaluate


def choose_action(state, share, eligible_amount):
    owed=min(state['amount_owed'],state['your_stack'])
    threshold=owed/max(1,eligible_amount)
    minimum=state['min_raise_to']
    effective=min(state['your_stack']+state['your_bet_this_street'],state['max_raise_to'])
    opponents=[p['stack']+p['bet_this_street'] for p in state['players'] if p['seat']!=state['seat_to_act'] and not p['is_folded']]
    effective=min(effective,max(opponents,default=0))
    if minimum and effective>=minimum and share>=.70 and share>=threshold+.15:
        amount=min(effective,max(minimum,state['current_bet']+(state['pot']+owed)//2))
        return {'action':'raise','amount':amount}
    if state['can_check']:
        return {'action':'check'}
    return {'action':'call'} if share>=threshold+.05 else {'action':'fold'}


def decide(state, *, clock=time.monotonic, rng=None):
    rng=rng or random.SystemRandom()
    deadline=clock()+1.0
    own=state['seat_to_act']
    live=[p for p in state['players'] if not p['is_folded']]
    known=state['your_cards']+state['community_cards']
    deck=[c for c in deck_for('double_joker') if c not in known]
    paid={p['seat']:p['paid']+(min(state['amount_owed'],state['your_stack']) if p['seat']==own else 0) for p in state['players']}
    pots=[];floor=0
    for level in sorted(set(paid.values())):
        if level<=0:continue
        contributors=[s for s,n in paid.items() if n>=level]
        amount=(level-floor)*len(contributors);floor=level
        if own in contributors and len(contributors)>1:
            pots.append((amount,[p['seat'] for p in live if paid[p['seat']]>=level]))
    eligible_amount=sum(n for n,_ in pots)
    if not eligible_amount:
        return {'action':'check' if state['can_check'] else 'fold'}
    total=0.0;samples=0
    others=[p['seat'] for p in live if p['seat']!=own]
    missing=5-len(state['community_cards'])
    for _ in range(2000):
        if clock()>=deadline:break
        draw=rng.sample(deck,missing+len(others)*2)
        board=state['community_cards']+draw[:missing]
        scores={own:evaluate(state['your_cards']+board)}
        for i,seat in enumerate(others):
            scores[seat]=evaluate(draw[missing+2*i:missing+2*i+2]+board)
        for amount,seats in pots:
            best=max(scores[s] for s in seats)
            winners=[s for s in seats if scores[s]==best]
            if own in winners:total+=amount/len(winners)
        samples+=1
    if not samples:
        return {'action':'check' if state['can_check'] else 'fold'}
    return choose_action(state,total/samples/eligible_amount,eligible_amount)