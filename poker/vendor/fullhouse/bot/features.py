"""Shared feature encoding used by training and runtime.

Feature vector layout (51 dimensions):
  CARD (17)         [0-16]   hand quality, draws, board texture
  POSITION/STREET  [17-26]  street + position one-hots
  STACK/POT (9)    [27-35]  pot, stack, SPR, pot odds, opponent stacks
  BETTING (10)     [36-45]  raises, invested chips, sizing, active players
  LEGAL (5)        [46-50]  fold, call, bet half-pot, bet pot, all-in
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

FEATURE_DIM = 51
N_ACTIONS = 5
STARTING_STACK = 10_000
BIG_BLIND = 100
LEGAL_MASK_OFFSET = 46

# State array offsets mirror training/game.py.
S_STACKS = 0
S_BETS = 6
S_INVESTED = 12
S_FOLDED = 18
S_ALLIN = 24
S_POT = 36
S_CURBET = 37
S_NRAISES = 38
S_LASTRAISER = 39
S_TOACT = 40
S_STREET = 41
S_DEALER = 43
S_NPLAYERS = 44


def _default_data_dir() -> Path:
    here = Path(__file__).resolve().parent
    candidates = (here / "data", here.parent / "data")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


_DATA_DIR = Path(os.environ.get("BOT_DATA_DIR", str(_default_data_dir())))

_EQUITY_PAIRED: np.ndarray | None = None
_EQUITY_SUITED: np.ndarray | None = None
_EQUITY_OFFSUIT: np.ndarray | None = None
_EVAL7 = None
_EVAL7_CARD_CACHE: list | None = None


def load_preflop_equity(
    path: Path | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    global _EQUITY_PAIRED, _EQUITY_SUITED, _EQUITY_OFFSUIT
    if _EQUITY_PAIRED is not None:
        return _EQUITY_PAIRED, _EQUITY_SUITED, _EQUITY_OFFSUIT
    if path is None:
        path = _DATA_DIR / "preflop_equity.npz"
    if not path.exists():
        raise FileNotFoundError(
            f"Preflop equity table not found at {path}. "
            "Run: python scripts/gen_preflop_equity.py"
        )
    data = np.load(path)
    _EQUITY_PAIRED = data["paired"]
    _EQUITY_SUITED = data["suited"]
    _EQUITY_OFFSUIT = data["offsuit"]
    return _EQUITY_PAIRED, _EQUITY_SUITED, _EQUITY_OFFSUIT


def _eval7_cards():
    global _EVAL7, _EVAL7_CARD_CACHE
    if _EVAL7_CARD_CACHE is not None:
        return _EVAL7_CARD_CACHE
    try:
        import eval7 as eval7_module
    except ImportError as exc:
        raise RuntimeError("eval7 is required for feature encoding") from exc
    _EVAL7 = eval7_module
    _EVAL7_CARD_CACHE = [
        eval7_module.Card(r + s) for s in "cdhs" for r in "23456789TJQKA"
    ]
    return _EVAL7_CARD_CACHE


_MAX_EVAL7_SCORE = 135004160.0


def infer_dealer(state: dict, n_players: int | None = None) -> int:
    """Infer dealer seat from state.

    The vendored engine omits ``dealer`` from action-request states, but it does
    include blind posts in ``action_log``. Training position features are dealer
    relative, so falling back to zero corrupts most runtime states.
    """
    if n_players is None:
        n_players = len(state.get("players", [])) or 2
    n_players = max(int(n_players), 2)

    if state.get("dealer") is not None:
        return int(state.get("dealer", 0)) % n_players

    small_blind = None
    big_blind = None
    for entry in state.get("action_log") or []:
        action = entry.get("action")
        if action == "small_blind" and entry.get("seat") is not None:
            small_blind = int(entry["seat"])
        elif action == "big_blind" and entry.get("seat") is not None:
            big_blind = int(entry["seat"])
        if small_blind is not None and big_blind is not None:
            break

    if small_blind is not None:
        if n_players == 2:
            return small_blind % n_players
        return (small_blind - 1) % n_players
    if big_blind is not None:
        if n_players == 2:
            return (big_blind - 1) % n_players
        return (big_blind - 2) % n_players
    import logging

    logging.getLogger(__name__).warning(
        "infer_dealer: no dealer or blind info in state, falling back to seat 0"
    )
    return 0


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _street_action_segment(log: list[dict]) -> list[dict]:
    """Return actions after the latest street marker when one is available."""
    for i in range(len(log) - 1, -1, -1):
        if log[i].get("action") == "deal":
            return log[i + 1 :]
    return log


def _street_index(street_name: str) -> int:
    return {"preflop": 0, "flop": 1, "turn": 2, "river": 3}.get(street_name, 0)


def _replay_betting_rounds(
    log: list[dict],
    players: list[dict],
    current_street_name: str,
) -> tuple[list[dict], dict[int, int], int, int | None, int]:
    """Replay action_log enough to recover street-local betting state.

    The real engine records street changes in ``events`` but exposes only player
    actions in ``action_log``. When those ``deal`` markers are missing at
    runtime, we infer street boundaries from betting-round closure so the bot
    stays aligned with the same legal-action rules used during training.
    """
    target_street = _street_index(current_street_name)
    seats = {int(p.get("seat", idx)) for idx, p in enumerate(players)}
    if not seats:
        seats = {int(e["seat"]) for e in log if e.get("seat") is not None}

    street = 0
    current_bet = 0
    last_full_raise = BIG_BLIND
    street_bets: dict[int, int] = {}
    invested: dict[int, int] = {}
    folded: set[int] = set()
    all_in: set[int] = set()
    pending: set[int] = set(seats)
    current_segment: list[dict] = []
    current_n_raises = 0
    current_last_raiser: int | None = None

    def active_seats() -> set[int]:
        return {seat for seat in seats if seat not in folded and seat not in all_in}

    def advance_street() -> None:
        nonlocal street, current_bet, last_full_raise, street_bets, pending
        street = min(street + 1, 3)
        current_bet = 0
        last_full_raise = BIG_BLIND
        street_bets = {}
        pending = active_seats()

    for entry in log:
        action = entry.get("action")
        if action == "deal":
            advance_street()
            continue
        if entry.get("seat") is None:
            continue
        seat = int(entry["seat"])
        seats.add(seat)
        amount = max(_safe_int(entry.get("amount", 0)), 0)

        if (
            action not in ("small_blind", "big_blind")
            and not pending
            and street < target_street
        ):
            advance_street()

        if street == target_street:
            current_segment.append(entry)

        if action in ("small_blind", "big_blind"):
            inc = amount
            street_bets[seat] = street_bets.get(seat, 0) + inc
            current_bet = max(current_bet, street_bets[seat])
        elif action == "fold":
            inc = 0
            folded.add(seat)
            pending.discard(seat)
        elif action == "check":
            inc = 0
            pending.discard(seat)
        elif action == "call":
            inc = amount
            street_bets[seat] = street_bets.get(seat, 0) + inc
            pending.discard(seat)
        elif action in ("raise", "all_in"):
            prev_bet = current_bet
            prev_seat_bet = street_bets.get(seat, 0)
            inc = max(0, amount - prev_seat_bet)
            street_bets[seat] = max(prev_seat_bet, amount)
            current_bet = max(current_bet, street_bets[seat])
            pending.discard(seat)
            if action == "all_in":
                all_in.add(seat)

            raise_size = max(0, current_bet - prev_bet)
            full_raise = raise_size >= last_full_raise
            if raise_size > 0 and full_raise:
                last_full_raise = raise_size
                pending = {s for s in active_seats() if s != seat}
                if street == target_street:
                    current_n_raises += 1
                    current_last_raiser = seat
        else:
            inc = 0
            pending.discard(seat)

        if inc:
            invested[seat] = invested.get(seat, 0) + inc

    if target_street == 0 and current_bet <= BIG_BLIND:
        current_n_raises = 0
        current_last_raiser = None
    return (
        current_segment,
        invested,
        min(current_n_raises, 4),
        current_last_raiser,
        last_full_raise,
    )


def _current_street_aggression(
    log: list[dict],
    players: list[dict],
    current_bet: int,
    street_name: str,
) -> tuple[int, int | None, int]:
    """Return (n_raises, last_raiser, last_full_raise) for the current street."""
    blind_only = street_name == "preflop" and current_bet <= 100
    no_bet = current_bet <= 0 or blind_only
    if no_bet:
        return 0, None, BIG_BLIND

    if any(entry.get("action") == "deal" for entry in log):
        segment = _street_action_segment(log)
        n_raises = 0
        last_raiser = None
        street_current_bet = 0
        last_full_raise = BIG_BLIND
        for entry in segment:
            action = entry.get("action")
            if entry.get("seat") is None:
                continue
            seat = int(entry["seat"])
            amount = _safe_int(entry.get("amount", 0))
            if action in ("small_blind", "big_blind", "call"):
                street_current_bet = max(street_current_bet, amount)
                continue
            if action not in ("raise", "all_in"):
                continue
            raise_size = max(0, amount - street_current_bet)
            street_current_bet = max(street_current_bet, amount)
            if raise_size >= last_full_raise:
                last_full_raise = raise_size
                n_raises += 1
                last_raiser = seat
        if n_raises:
            return min(n_raises, 4), last_raiser, last_full_raise
        return 1, None, BIG_BLIND

    _, _, n_raises, last_raiser, last_full_raise = _replay_betting_rounds(
        log, players, street_name
    )
    if n_raises:
        return n_raises, last_raiser, last_full_raise

    # The engine can expose a current bet even when action_log lacks enough
    # street context to identify the exact bettor. Keep legal masking aligned
    # with the existence of an outstanding bet instead of pretending no
    # aggression happened.
    return 1, None, BIG_BLIND


def _hand_invested_from_log(
    log: list[dict],
    players: list[dict] | None = None,
    street_name: str = "preflop",
) -> dict[int, int]:
    """Approximate current-hand contributions from action_log.

    Raise/all-in amounts are total bet-to values for that street, so street
    markers or inferred street boundaries let this reconstruct total invested
    without relying on match stacks being reset to 10,000 every hand.
    """
    if players is not None and not any(entry.get("action") == "deal" for entry in log):
        _, invested, _, _, _ = _replay_betting_rounds(log, players, street_name)
        return invested

    invested: dict[int, int] = {}
    street_bets: dict[int, int] = {}

    for entry in log:
        action = entry.get("action")
        if action == "deal":
            street_bets.clear()
            continue
        if entry.get("seat") is None:
            continue
        seat = int(entry["seat"])
        amount = max(_safe_int(entry.get("amount", 0)), 0)
        if action in ("small_blind", "big_blind", "call"):
            inc = amount
            street_bets[seat] = street_bets.get(seat, 0) + inc
        elif action in ("raise", "all_in"):
            inc = max(0, amount - street_bets.get(seat, 0))
            street_bets[seat] = max(street_bets.get(seat, 0), amount)
        else:
            inc = 0
        if inc:
            invested[seat] = invested.get(seat, 0) + inc

    return invested


def _evaluate_hand_strength(c0: int, c1: int, board_idx: list[int]) -> float:
    cards = _eval7_cards()
    try:
        hand = [cards[c0], cards[c1]] + [cards[b] for b in board_idx]
        return _EVAL7.evaluate(hand) / _MAX_EVAL7_SCORE
    except Exception as exc:
        raise RuntimeError(
            f"eval7 hand evaluation failed for hole={[c0, c1]} board={board_idx}"
        ) from exc


def preflop_equity(card0: int, card1: int) -> float:
    """Lookup MC preflop equity from card indices (0-51)."""
    paired, suited, offsuit = load_preflop_equity()
    r0, r1 = card0 % 13, card1 % 13
    s0, s1 = card0 // 13, card1 // 13
    hi, lo = max(r0, r1), min(r0, r1)
    if r0 == r1:
        return float(paired[r0])
    elif s0 == s1:
        return float(suited[hi, lo])
    else:
        return float(offsuit[hi, lo])


def count_straight_out_ranks(rank_present: list[bool]) -> int:
    """Count distinct ranks that would complete a straight."""
    out_ranks = set()
    for start in range(9):
        present_count = 0
        missing = []
        for r in range(start, start + 5):
            if rank_present[r]:
                present_count += 1
            else:
                missing.append(r)
        if present_count == 4:
            out_ranks.update(missing)
    # Wheel: A-2-3-4-5 (ranks 12, 0, 1, 2, 3)
    wheel = [12, 0, 1, 2, 3]
    present_count = sum(1 for r in wheel if rank_present[r])
    if present_count == 4:
        for r in wheel:
            if not rank_present[r]:
                out_ranks.add(r)
    return len(out_ranks)


def detect_draws(
    hole_indices: list[int],
    board_indices: list[int],
    street: int,
) -> tuple[bool, bool, bool, int, bool]:
    """Detect draws from card indices (0-51).

    Returns (flush_draw, oesd, gutshot, draw_outs, nut_flush_draw).
    All draw indicators are False on the river (street == 3).
    """
    if street >= 3 or not board_indices:
        return False, False, False, 0, False

    all_cards = hole_indices + board_indices

    # Flush draw
    suit_counts = [0, 0, 0, 0]
    for c in all_cards:
        suit_counts[c // 13] += 1
    max_suit_count = max(suit_counts)
    flush_draw = max_suit_count == 4
    flush_suit = suit_counts.index(max_suit_count) if flush_draw else -1

    # Nut flush draw: hero holds highest card of the flush suit
    nut_flush_draw = False
    if flush_draw:
        flush_cards_on_board = [c % 13 for c in board_indices if c // 13 == flush_suit]
        flush_cards_hero = [c % 13 for c in hole_indices if c // 13 == flush_suit]
        if flush_cards_hero:
            all_flush_ranks = flush_cards_on_board + flush_cards_hero
            nut_flush_draw = max(flush_cards_hero) == max(all_flush_ranks)

    # Straight draw
    rank_present = [False] * 13
    for c in all_cards:
        rank_present[c % 13] = True

    straight_out_ranks = count_straight_out_ranks(rank_present)
    oesd = straight_out_ranks >= 2
    gutshot = straight_out_ranks == 1

    # Count total outs
    flush_outs = 9 if flush_draw else 0
    straight_outs = straight_out_ranks * 4
    overlap = min(straight_out_ranks, 2) if flush_draw and straight_out_ranks > 0 else 0
    draw_outs = flush_outs + straight_outs - overlap

    return flush_draw, oesd, gutshot, draw_outs, nut_flush_draw


def board_texture(board_indices: list[int]) -> tuple[bool, bool, float, bool]:
    """Compute board texture features.

    Returns (board_paired, board_monotone, board_wet, straight_possible).
    """
    if not board_indices:
        return False, False, 0.0, False

    ranks = [c % 13 for c in board_indices]
    suits = [c // 13 for c in board_indices]

    # Paired
    rank_set = set(ranks)
    paired = len(rank_set) < len(ranks)

    # Monotone: all board cards share a suit
    monotone = len(set(suits)) == 1

    # Wet: fraction of board card pairs within 2 ranks of each other
    n = len(ranks)
    if n < 2:
        wet = 0.0
    else:
        close_pairs = 0
        total_pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                total_pairs += 1
                if abs(ranks[i] - ranks[j]) <= 2:
                    close_pairs += 1
        wet = close_pairs / total_pairs

    # Straight possible: 3+ board cards fit in one 5-rank window
    rank_present = [False] * 13
    for r in ranks:
        rank_present[r] = True
    straight_possible = False
    for start in range(9):
        count = sum(1 for r in range(start, start + 5) if rank_present[r])
        if count >= 3:
            straight_possible = True
            break
    if not straight_possible:
        # Wheel
        wheel_count = sum(1 for r in (12, 0, 1, 2, 3) if rank_present[r])
        if wheel_count >= 3:
            straight_possible = True

    return paired, monotone, wet, straight_possible


def encode_state(
    state: np.ndarray,
    hole_cards: np.ndarray,
    deck: np.ndarray,
    seat: int,
    legal: np.ndarray,
    equity_tables: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    if equity_tables is None:
        equity_tables = load_preflop_equity()
    eq_paired, eq_suited, eq_offsuit = equity_tables

    features = np.zeros(FEATURE_DIM, dtype=np.float32)
    n = state[S_NPLAYERS]
    street = state[S_STREET]

    c0 = int(hole_cards[seat, 0])
    c1 = int(hole_cards[seat, 1])
    r0, r1 = c0 % 13, c1 % 13
    s0, s1 = c0 // 13, c1 // 13
    hi, lo = max(r0, r1), min(r0, r1)

    board_start = 2 * n
    n_board = (0, 3, 4, 5)[street]
    board_idx = [int(deck[board_start + b]) for b in range(n_board)]

    if r0 == r1:
        features[0] = eq_paired[r0]
    elif s0 == s1:
        features[0] = eq_suited[hi, lo]
    else:
        features[0] = eq_offsuit[hi, lo]

    if street > 0 and board_idx:
        features[1] = _evaluate_hand_strength(c0, c1, board_idx)

    fd, oesd, gs, outs, nfd = detect_draws([c0, c1], board_idx, street)
    features[2] = 1.0 if fd else 0.0
    features[3] = 1.0 if oesd else 0.0
    features[4] = 1.0 if gs else 0.0
    features[5] = outs / 20.0
    features[6] = 1.0 if nfd else 0.0

    features[7] = hi / 12.0
    features[8] = lo / 12.0
    features[9] = 1.0 if s0 == s1 else 0.0
    features[10] = 1.0 if r0 == r1 else 0.0
    features[11] = (hi - lo - 1) / 12.0 if hi != lo else 0.0

    if board_idx:
        bp, bm, bw, sp = board_texture(board_idx)
        features[12] = 1.0 if bp else 0.0
        features[13] = 1.0 if bm else 0.0
        board_ranks = [b % 13 for b in board_idx]
        features[14] = sum(1 for br in board_ranks if br > hi) / 5.0
        features[15] = bw
        features[16] = 1.0 if sp else 0.0

    features[17 + street] = 1.0
    pos = (seat - state[S_DEALER]) % n
    features[21 + min(pos, 5)] = 1.0

    pot = state[S_POT]
    my_stack = state[S_STACKS + seat]
    features[27] = pot / STARTING_STACK
    features[28] = my_stack / STARTING_STACK

    min_stack = min(
        (int(state[S_STACKS + i]) for i in range(n) if state[S_FOLDED + i] == 0),
        default=0,
    )
    spr = min_stack / max(pot, 1)
    features[29] = min(spr, 10.0) / 10.0

    to_call = max(0, state[S_CURBET] - state[S_BETS + seat])
    features[30] = to_call / (pot + to_call) if (pot + to_call) > 0 else 0.0

    opp_stacks = []
    for i in range(n):
        if i != seat and state[S_FOLDED + i] == 0:
            opp_stacks.append(state[S_STACKS + i])
    opp_stacks.sort(reverse=True)
    for i in range(min(len(opp_stacks), 5)):
        features[31 + i] = opp_stacks[i] / STARTING_STACK

    features[36] = min(state[S_NRAISES], 4) / 4.0
    features[37] = 1.0 if state[S_LASTRAISER] >= 0 else 0.0
    features[38] = 1.0 if state[S_LASTRAISER] == seat else 0.0
    features[39] = state[S_BETS + seat] / STARTING_STACK
    features[40] = state[S_INVESTED + seat] / STARTING_STACK
    features[41] = state[S_CURBET] / max(pot, 1)
    features[42] = to_call / max(my_stack, 1)

    max_vill_bets = 0
    max_vill_invested = 0
    for i in range(n):
        if i != seat and state[S_FOLDED + i] == 0:
            if state[S_BETS + i] > max_vill_bets:
                max_vill_bets = state[S_BETS + i]
            if state[S_INVESTED + i] > max_vill_invested:
                max_vill_invested = state[S_INVESTED + i]
    features[43] = max_vill_bets / STARTING_STACK
    features[44] = max_vill_invested / STARTING_STACK

    n_active = sum(1 for i in range(n) if state[S_FOLDED + i] == 0)
    features[45] = n_active / 6.0

    for a in range(N_ACTIONS):
        features[LEGAL_MASK_OFFSET + a] = float(legal[a])

    return features


def encode_state_dict(
    state: dict,
    equity_tables: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if equity_tables is None:
        equity_tables = load_preflop_equity()
    eq_paired, eq_suited, eq_offsuit = equity_tables

    _RANK_ORDER = "23456789TJQKA"
    _SUIT_ORDER = "cdhs"

    def card_to_idx(card_str: str) -> int:
        return _SUIT_ORDER.index(card_str[1]) * 13 + _RANK_ORDER.index(card_str[0])

    features = np.zeros(FEATURE_DIM, dtype=np.float32)

    my_cards = state["your_cards"]
    community = state.get("community_cards", [])
    players = state.get("players", [])
    my_seat = state["seat_to_act"]
    n_players = len(players)
    dealer = infer_dealer(state, n_players)
    street_name = state.get("street", "preflop")
    street = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}[street_name]
    pot = state.get("pot", 0)
    my_stack = state.get("your_stack", STARTING_STACK)
    to_call = state.get("amount_owed", 0)
    current_bet = state.get("current_bet", 0)

    c0 = card_to_idx(my_cards[0])
    c1 = card_to_idx(my_cards[1])
    r0, r1 = c0 % 13, c1 % 13
    s0, s1 = c0 // 13, c1 // 13
    hi, lo = max(r0, r1), min(r0, r1)
    board_idx = [card_to_idx(c) for c in community]

    if r0 == r1:
        features[0] = eq_paired[r0]
    elif s0 == s1:
        features[0] = eq_suited[hi, lo]
    else:
        features[0] = eq_offsuit[hi, lo]

    if street > 0 and community:
        features[1] = _evaluate_hand_strength(c0, c1, board_idx)

    fd, oesd, gs, outs, nfd = detect_draws([c0, c1], board_idx, street)
    features[2] = 1.0 if fd else 0.0
    features[3] = 1.0 if oesd else 0.0
    features[4] = 1.0 if gs else 0.0
    features[5] = outs / 20.0
    features[6] = 1.0 if nfd else 0.0

    features[7] = hi / 12.0
    features[8] = lo / 12.0
    features[9] = 1.0 if s0 == s1 else 0.0
    features[10] = 1.0 if r0 == r1 else 0.0
    features[11] = (hi - lo - 1) / 12.0 if hi != lo else 0.0

    if board_idx:
        bp, bm, bw, sp = board_texture(board_idx)
        features[12] = 1.0 if bp else 0.0
        features[13] = 1.0 if bm else 0.0
        board_ranks = [b % 13 for b in board_idx]
        features[14] = sum(1 for br in board_ranks if br > hi) / 5.0
        features[15] = bw
        features[16] = 1.0 if sp else 0.0

    features[17 + street] = 1.0
    pos = (my_seat - dealer) % max(n_players, 2)
    features[21 + min(pos, 5)] = 1.0

    features[27] = pot / STARTING_STACK
    features[28] = my_stack / STARTING_STACK

    active_stacks = [p.get("stack", 0) for p in players if not p.get("is_folded")]
    min_stack = min(active_stacks) if active_stacks else 0
    spr = min_stack / max(pot, 1)
    features[29] = min(max(spr, 0.0), 10.0) / 10.0

    features[30] = (
        to_call / (pot + to_call) if to_call > 0 and (pot + to_call) > 0 else 0.0
    )

    opp_stacks = sorted(
        [
            p.get("stack", 0)
            for p in players
            if p.get("seat") != my_seat and not p.get("is_folded")
        ],
        reverse=True,
    )
    for i in range(min(len(opp_stacks), 5)):
        features[31 + i] = opp_stacks[i] / STARTING_STACK

    log = state.get("action_log") or []
    n_raises, last_raiser, last_full_raise = _current_street_aggression(
        log, players, current_bet, street_name
    )
    has_aggressor = last_raiser is not None or (
        current_bet > 0 and not (street_name == "preflop" and current_bet <= 100)
    )

    features[36] = min(n_raises, 4) / 4.0
    features[37] = 1.0 if has_aggressor else 0.0
    features[38] = 1.0 if last_raiser == my_seat else 0.0
    features[39] = state.get("your_bet_this_street", 0) / STARTING_STACK
    hand_invested = _hand_invested_from_log(log, players, street_name)
    if hand_invested:
        invested = hand_invested.get(my_seat, 0)
    else:
        invested = STARTING_STACK - my_stack
    features[40] = invested / STARTING_STACK
    features[41] = current_bet / max(pot, 1)
    features[42] = to_call / max(my_stack, 1)

    max_vill_bets = 0
    max_vill_invested = 0
    for p in players:
        if p.get("seat") != my_seat and not p.get("is_folded"):
            max_vill_bets = max(max_vill_bets, _safe_int(p.get("bet_this_street", 0)))
            seat = _safe_int(p.get("seat", -1), -1)
            if hand_invested:
                vi = hand_invested.get(seat, 0)
            else:
                vi = STARTING_STACK - p.get("stack", STARTING_STACK)
            if vi > max_vill_invested:
                max_vill_invested = vi
    features[43] = max_vill_bets / STARTING_STACK
    features[44] = max_vill_invested / STARTING_STACK

    n_active = sum(1 for p in players if not p.get("is_folded"))
    features[45] = n_active / 6.0

    legal_mask = _compute_legal_mask(state, n_raises, last_full_raise)
    for a in range(N_ACTIONS):
        features[LEGAL_MASK_OFFSET + a] = float(legal_mask[a])

    return features, legal_mask


def _compute_legal_mask(
    state: dict,
    n_raises: int = 0,
    last_full_raise: int = BIG_BLIND,
) -> np.ndarray:
    SPR_ALLIN_THRESHOLD = 4

    legal = np.zeros(N_ACTIONS, dtype=np.bool_)
    owed = state.get("amount_owed", 0)
    stack = state.get("your_stack", 0)
    pot = state.get("pot", 0)
    min_raise = state.get("min_raise_to", 0)
    players = state.get("players", [])
    my_seat = state.get("seat_to_act", 0)
    last_full_raise = max(_safe_int(last_full_raise, BIG_BLIND), BIG_BLIND)

    if owed > 0:
        legal[0] = True
    legal[1] = True

    can_raise = stack > owed and min_raise > 0
    if can_raise:
        pot_after_call = pot + owed
        bet_room = stack - owed
        bet_50 = round(0.50 * pot_after_call)
        if bet_50 >= last_full_raise and bet_room > bet_50:
            legal[2] = True
        if pot_after_call >= last_full_raise and bet_room > pot_after_call:
            legal[3] = True
        opp_stacks = [
            p.get("stack", 0)
            for p in players
            if p.get("seat") != my_seat and not p.get("is_folded")
        ]
        max_opp = max(opp_stacks) if opp_stacks else 0
        eff_stack = min(stack, max_opp) if max_opp > 0 else stack
        spr = eff_stack / max(pot, 1)
        if spr < SPR_ALLIN_THRESHOLD:
            legal[4] = True

    return legal
