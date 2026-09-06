"""Original crystal reward rules, independent of Discord and storage."""

import math
import random
from datetime import date
from typing import Iterable

CRYSTAL_EMOJI = "<:crystal:431483260468592641>"
DOUBLE_ROLE_ID = 586253482227400912
LEVEL_ROLES = {
    "LV.150 女武神．愛醬": 150,
    "LV.80 血色玫瑰": 80,
    "LV.76 次元邊界突破": 76,
    "LV.72 血騎士．月煌": 72,
    "LV.68 雷電女王的鬼鎧": 68,
    "LV.64 白騎士．月光": 64,
    "LV.60 異度黑核侵蝕": 60,
    "LV.56 銀狼的黎明": 56,
    "LV.52 女武神．凱旋": 52,
    "LV.48 雪地狙擊": 48,
    "LV.44 影舞衝擊": 44,
    "LV.40 聖女祈禱": 40,
    "LV.35 融核裝．深紅": 35,
    "LV.30 驅動裝．山吹": 30,
    "LV.25 女武神．遊俠": 25,
    "LV.20 女武神．強襲": 20,
    "LV.15 戰場疾風": 15,
    "LV.10 女武神．戰車": 10,
    "LV.5 脈衝裝．緋紅": 5,
    "LV.1 領域裝．白練": 1,
}


def level_for_roles(names: Iterable[str]) -> int:
    return max((LEVEL_ROLES.get(name, 1) for name in names), default=1)


def daily_reward(level: int, doubled: bool, *, sample: float | None = None) -> int:
    if level not in LEVEL_ROLES.values():
        raise ValueError("Unsupported crystal level.")
    value = random.random() if sample is None else sample
    if not 0 <= value < 1:
        raise ValueError("Random sample must be in [0, 1).")
    amount = math.floor(value * level * 2.5 + math.ceil(level / 1.5))
    return amount * (2 if doubled else 1)


def can_claim(last_claim: date | None, today: date) -> bool:
    return last_claim is None or last_claim < today


def is_crystal_message(content: str) -> bool:
    return content.strip() == CRYSTAL_EMOJI
