"""Deep CFR 6-max NLHE poker bot."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from bot.features import (
    _compute_legal_mask,
    _current_street_aggression,
    _default_data_dir,
    infer_dealer,
)

BOT_NAME = "fullhouse-deep-cfr"
BOT_AVATAR = "robot_1"

SMALL_BLIND = 50
BIG_BLIND = 100
STARTING_STACK = 10_000

POSITIONS_6MAX = ("BTN", "SB", "BB", "LJ", "HJ", "CO")

_RANK_ORDER = "23456789TJQKA"
_RANK_VAL = {r: i for i, r in enumerate(_RANK_ORDER)}

FOLD, CHECK_CALL, BET_50, BET_POT, ALL_IN = range(5)
N_ACTIONS = 5


_DATA_DIR = Path(os.environ.get("BOT_DATA_DIR", str(_default_data_dir())))

_RNG = random.Random(0xC0FFEE)


_RUNTIME_WARMED = False


def _warm_runtime() -> None:
    global _RUNTIME_WARMED
    if _RUNTIME_WARMED:
        return
    try:
        import eval7

        _ = eval7.Card("As")
        _ = eval7.evaluate(
            [
                eval7.Card("As"),
                eval7.Card("Kd"),
                eval7.Card("Qh"),
                eval7.Card("Jc"),
                eval7.Card("Tc"),
                eval7.Card("9s"),
                eval7.Card("2d"),
            ]
        )
    except Exception:
        pass
    _RUNTIME_WARMED = True


from bot.deep_cfr_lookup import DeepCFRLookup

_dcfr_paths = sorted(_DATA_DIR.glob("deep_cfr_model*.npz"))
if not _dcfr_paths:
    raise FileNotFoundError(f"No Deep CFR model snapshots found in {_DATA_DIR}")
if len(_dcfr_paths) == 1:
    _DEEP_CFR = DeepCFRLookup(str(_dcfr_paths[0]))
else:
    _DEEP_CFR = DeepCFRLookup([str(p) for p in _dcfr_paths])
_warm_runtime()


def _hand_class(cards: list[str]) -> str:
    r0, s0 = cards[0][0], cards[0][1]
    r1, s1 = cards[1][0], cards[1][1]
    if _RANK_VAL[r0] < _RANK_VAL[r1]:
        r0, r1 = r1, r0
        s0, s1 = s1, s0
    if r0 == r1:
        return r0 + r1
    return r0 + r1 + ("s" if s0 == s1 else "o")


def _position(state: dict) -> str:
    n = len(state.get("players", []))
    seat = state["seat_to_act"]
    dealer = infer_dealer(state, max(n, 2))
    if n == 2:
        return "BTN" if seat == dealer else "BB"
    if n == 3:
        return ("BTN", "SB", "BB")[(seat - dealer) % n]
    if n == 4:
        return ("BTN", "SB", "BB", "CO")[(seat - dealer) % n]
    if n == 5:
        return ("BTN", "SB", "BB", "HJ", "CO")[(seat - dealer) % n]
    if n >= 6:
        offset = (seat - dealer) % n
        return POSITIONS_6MAX[offset]
    offset = (seat - dealer) % n
    if offset == 0:
        return "BTN"
    if offset == n - 1:
        return "BB"
    if offset == n - 2:
        return "SB"
    return "CO"


_PF_TIER1 = {
    "AA",
    "KK",
    "QQ",
    "JJ",
    "TT",
    "99",
    "88",
    "77",
    "AKs",
    "AKo",
    "AQs",
    "AQo",
    "AJs",
    "ATs",
    "AJo",
    "KQs",
    "KJs",
    "KQo",
    "ATo",
    "A9s",
    "A8s",
    "A7s",
    "A6s",
    "A5s",
    "A4s",
    "A3s",
    "A2s",
}
_PF_TIER2 = _PF_TIER1 | {
    "66",
    "55",
    "44",
    "33",
    "22",
    "KTs",
    "K9s",
    "K8s",
    "QJs",
    "QTs",
    "Q9s",
    "JTs",
    "J9s",
    "T9s",
    "T8s",
    "98s",
    "87s",
    "76s",
    "KJo",
    "KTo",
    "QJo",
    "QTo",
    "JTo",
    "A9o",
    "A8o",
}
_PF_TIER3 = _PF_TIER2 | {
    "K7s",
    "K6s",
    "K5s",
    "K4s",
    "K3s",
    "K2s",
    "Q8s",
    "Q7s",
    "Q6s",
    "J8s",
    "J7s",
    "T7s",
    "97s",
    "86s",
    "75s",
    "65s",
    "54s",
    "K9o",
    "K8o",
    "Q9o",
    "J9o",
    "T9o",
    "98o",
    "87o",
    "A7o",
    "A6o",
    "A5o",
    "A4o",
    "A3o",
    "A2o",
}
_PF_CALL_TIGHT = {
    "AA",
    "KK",
    "QQ",
    "JJ",
    "TT",
    "99",
    "88",
    "77",
    "AKs",
    "AKo",
    "AQs",
    "AQo",
    "AJs",
    "ATs",
    "A9s",
    "KQs",
    "KJs",
    "KTs",
    "QJs",
}
_PF_CALL_MEDIUM = _PF_CALL_TIGHT | {
    "66",
    "55",
    "44",
    "AJo",
    "ATo",
    "A8s",
    "A7s",
    "A6s",
    "A5s",
    "KQo",
    "KJo",
    "QTs",
    "JTs",
    "T9s",
}
_PF_CALL_WIDE = _PF_CALL_MEDIUM | {
    "33",
    "22",
    "A4s",
    "A3s",
    "A2s",
    "K9s",
    "QJo",
    "Q9s",
    "J9s",
    "A9o",
    "A8o",
    "A7o",
}


def _push_fold(state: dict) -> dict | None:
    stack = state["your_stack"]
    players = state.get("players", [])
    my_seat = state["seat_to_act"]
    max_opp = max(
        (
            p.get("stack", 0) or 0
            for p in players
            if p.get("seat") != my_seat and not p.get("is_folded")
        ),
        default=stack,
    )
    eff_bb = min(stack, max_opp) / BIG_BLIND
    if eff_bb > 12:
        return None

    hclass = _hand_class(state["your_cards"])
    pos = _position(state)
    owed = state.get("amount_owed", 0)

    if owed > 0:
        pot_odds = owed / (state["pot"] + owed) if (state["pot"] + owed) > 0 else 1.0
        if hclass in _PF_TIER1:
            return {"action": "all_in"}
        if eff_bb <= 6:
            call_range = _PF_CALL_MEDIUM if pot_odds < 0.35 else _PF_CALL_TIGHT
        elif eff_bb <= 10:
            call_range = _PF_CALL_WIDE if pot_odds < 0.35 else _PF_CALL_MEDIUM
        else:
            call_range = _PF_CALL_WIDE
        if hclass in call_range:
            return {"action": "call"}
        return {"action": "fold"}

    push_range = (
        _PF_TIER1
        if pos in ("LJ", "HJ")
        else (
            _PF_TIER2
            if pos == "CO"
            else _PF_TIER3
            if pos in ("BTN", "SB")
            else _PF_CALL_WIDE
        )
    )
    if hclass in push_range:
        return {"action": "all_in"}
    if state.get("can_check", False):
        return {"action": "check"}
    return {"action": "fold"}


def _apply_legal_mask(strategy: np.ndarray, state: dict) -> np.ndarray:
    if not np.isfinite(strategy).all():
        raise FloatingPointError(
            "strategy contains non-finite values before legal masking"
        )

    masked = strategy.copy()
    n = len(masked)
    log = state.get("action_log") or []
    players = state.get("players") or []
    n_raises, _, last_full_raise = _current_street_aggression(
        log,
        players,
        state.get("current_bet", 0),
        state.get("street", "preflop"),
    )
    legal = _compute_legal_mask(state, n_raises, last_full_raise).astype(np.float32)
    if n != len(legal):
        legal = legal[:n]
    masked *= legal

    total = masked.sum()
    if total > 0:
        return masked / total
    if legal.sum() == 1.0:
        return legal / legal.sum()
    raise RuntimeError(
        f"legal masking removed all probability mass for state={state} strategy={strategy}"
    )


def _safe_default_action(state: dict) -> dict:
    if state.get("can_check", False):
        return {"action": "check"}
    owed = int(state.get("amount_owed", state.get("to_call", 0)) or 0)
    stack = int(state.get("your_stack", 0) or 0)
    if owed > 0 and stack > 0:
        return {"action": "call"}
    return {"action": "fold"}


def decide(state: dict) -> dict:
    _warm_runtime()
    if state.get("type") == "warmup":
        return _safe_default_action(state)

    try:
        street = state.get("street", "preflop")

        if street == "preflop":
            pf = _push_fold(state)
            if pf is not None:
                return pf

        strategy = _DEEP_CFR.get_strategy(state)
        strategy = _apply_legal_mask(strategy, state)
        action_id = _sample(strategy)
        return _to_engine_action(action_id, state)
    except Exception:
        return _safe_default_action(state)


def _sample(probs: np.ndarray) -> int:
    if probs.ndim != 1:
        raise ValueError(f"expected 1D probability vector, got shape={probs.shape}")
    if not np.isfinite(probs).all():
        raise FloatingPointError("cannot sample from non-finite probabilities")
    if np.any(probs < 0):
        raise ValueError(f"cannot sample from negative probabilities: {probs}")
    total = float(probs.sum())
    if not np.isclose(total, 1.0, atol=1e-5):
        raise ValueError(f"probabilities must sum to 1, got {total} from {probs}")

    r = _RNG.random()
    cumsum = 0.0
    for i in range(len(probs)):
        cumsum += float(probs[i])
        if r < cumsum:
            return i
    if cumsum >= 1.0 - 1e-7:
        return len(probs) - 1
    raise RuntimeError(
        f"sampling failed: cumulative mass ended at {cumsum} for probs={probs}"
    )


def _to_engine_action(action_id: int, state: dict) -> dict:
    if action_id == FOLD:
        if state.get("can_check"):
            return {"action": "check"}
        return {"action": "fold"}
    if action_id == CHECK_CALL:
        if state.get("can_check"):
            return {"action": "check"}
        return {"action": "call"}
    if action_id == ALL_IN:
        return {"action": "all_in"}

    frac = {BET_50: 0.50, BET_POT: 1.0}.get(action_id)
    if frac is None:
        raise ValueError(f"unknown action id {action_id}")

    pot = state.get("pot", 0)
    my_bet = state.get("your_bet_this_street", state.get("your_bet", 0))
    to_call = state.get("amount_owed", state.get("to_call", 0))
    stack = state.get("your_stack", 0)
    min_raise = state.get("min_raise_to", 0)

    pot_after_call = pot + to_call
    bet_amount = int(round(frac * pot_after_call))
    raise_to = my_bet + to_call + bet_amount
    max_raise = my_bet + stack
    raise_to = max(min_raise, min(raise_to, max_raise))

    if raise_to >= max_raise:
        return {"action": "all_in"}
    if raise_to <= my_bet + to_call:
        return {"action": "call"} if to_call > 0 else {"action": "check"}
    return {"action": "raise", "amount": raise_to}
