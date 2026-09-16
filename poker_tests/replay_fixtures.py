"""Offline, durable browser fixtures. Never imported by the production service."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

from poker import rules
from poker.store import Store

A, B, C = "111111111111111111", "222222222222222222", "333333333333333333"


async def seed(path):
    async with Store(path, initialize=True) as store:
        for user in (A, B, C):
            await store.login(user)
        for index in range(23):
            hand_id = f"archive-{index:02}"
            sizes = (
                [(A, 5000), (B, 2000), (C, 3000)]
                if index == 22
                else [(A, 2000), (B, 2000)]
            )
            for user, chips in sizes:
                await store.command(
                    f"{hand_id}-buy-{user}",
                    "buy_in",
                    user_id=user,
                    table_id="archive",
                    amount=str(chips),
                )
            draw = [
                "2c",
                "3c",
                "4c",
                "2d",
                "3d",
                "4d",
                "5c",
                "Ts",
                "Js",
                "Qs",
                "6c",
                "Ks",
                "7c",
                "As",
            ]

            def shuffle(deck):
                deck[:] = [c for c in rules.CARDS if c not in draw] + list(
                    reversed(draw)
                )

            with patch("secrets.SystemRandom.shuffle", side_effect=shuffle):
                hand = rules.create(sizes, 0, hand_id)
            if index == 22:
                for user in (A, B, C):
                    rules.act(hand, user, "all_in" if user == A else "call")
            else:
                rules.act(hand, A, "fold")
            if index == 0:
                hand.pop("replay_version")
            await store.command(
                hand_id + "-start",
                "start_hand",
                hand_id=hand_id,
                table_id="archive",
                players=[u for u, _ in sizes],
                snapshot=hand,
            )
            for p in hand["players"]:
                await store.command(
                    f"{hand_id}-bet-{p['id']}",
                    "bet",
                    hand_id=hand_id,
                    user_id=p["id"],
                    amount=str(p["paid"]),
                )
            await store.command(
                hand_id + "-settle",
                "settle",
                hand_id=hand_id,
                payouts={u: str(n) for u, n in hand["payouts"].items()},
                snapshot=hand,
            )
            for user, _ in sizes:
                await store.command(f"{hand_id}-leave-{user}", "leave", user_id=user)


if __name__ == "__main__":
    asyncio.run(seed(Path(sys.argv[1])))
