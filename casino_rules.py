"""Exact-integer bets and the specified three-dice ordering."""

from dataclasses import dataclass


class CasinoError(ValueError):
    """An expected, safe-to-display casino rejection."""


class InsufficientBalance(CasinoError):
    """A rejected wager that should be shown on the public owner panel."""


@dataclass(frozen=True)
class Bet:
    base: int = 10
    multiplier: int = 1

    def __post_init__(self):
        if type(self.base) is not int or self.base < 2 or self.base % 2:
            raise CasinoError("基本下注必須是至少 2 的偶數整數。")
        if type(self.multiplier) is not int or self.multiplier < 1:
            raise CasinoError("倍率必須是正整數。")

    @property
    def total(self) -> int:
        return self.base * self.multiplier


def parse_integer(value: str) -> int:
    value = value.strip()
    if not value or not value.isascii() or not value.isdecimal():
        raise CasinoError("請輸入十進位正整數，不接受小數或科學記號。")
    return int(value)


def dice_rank(dice) -> tuple[int, int, int]:
    if len(dice) != 3 or any(type(v) is not int or not 1 <= v <= 6 for v in dice):
        raise ValueError("Invalid persisted dice")
    values = sorted(dice)
    total = sum(values)
    if len(set(values)) == 1:
        return (4, values[0], total)
    if values == [4, 5, 6]:
        return (3, 0, total)
    if len(set(values)) == 2:
        single = next(v for v in values if values.count(v) == 1)
        return (2, single, total)
    if values == [1, 2, 3]:
        return (1, 0, total)
    return (0, 0, total)


def dice_points(dice) -> int:
    """Numeric score from mei-bot gamble.js; sum only breaks equal scores."""
    category, value, _ = dice_rank(dice)
    return {4: value * 10, 3: 7, 2: value, 1: 0, 0: -1}[category]


def outcome(player, dealer) -> str:
    left, right = dice_rank(player), dice_rank(dealer)
    return "win" if left > right else "loss" if left < right else "tie"
