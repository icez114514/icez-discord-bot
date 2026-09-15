import asyncio
import tempfile
import unittest
from pathlib import Path
from poker.store import Store, Conflict


class MoneyTests(unittest.IsolatedAsyncioTestCase):
    async def test_transfers_settlement_and_subsidy_are_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                for player in ("111", "222"):
                    await store.login(player)
                    await store.command(
                        "buy-" + player,
                        "buy_in",
                        user_id=player,
                        amount="10000",
                        table_id="a",
                    )
                await store.command(
                    "start",
                    "start_hand",
                    hand_id="h",
                    table_id="a",
                    players=["111", "222"],
                    snapshot={"version": 1},
                )
                await store.command(
                    "bet1", "bet", user_id="111", amount="10000", hand_id="h"
                )
                self.assertEqual((await store.account("111"))["settled"], "50000")
                with self.assertRaises(Conflict):
                    await store.command("early-help", "subsidy", user_id="111")
                with self.assertRaises(Conflict):
                    await store.command(
                        "bad-settle", "settle", hand_id="h", payouts={"222": "9999"}
                    )
                self.assertEqual((await store.account("111"))["in_flight"], "10000")
                settled = await store.command(
                    "finish", "settle", hand_id="h", payouts={"222": "10000"}
                )
                self.assertEqual(
                    await store.command(
                        "finish", "settle", hand_id="h", payouts={"222": "10000"}
                    ),
                    settled,
                )
                self.assertEqual((await store.account("111"))["settled"], "40000")
                self.assertEqual((await store.account("222"))["settled"], "60000")
                await store.command(
                    "adjust",
                    "adjust",
                    user_id="111",
                    amount="-39000",
                    reason="Test debit",
                    actor="999",
                )
                results = await asyncio.gather(
                    *(
                        store.command(
                            "help" + str(n), "subsidy", user_id="111", now=1789416000
                        )
                        for n in range(8)
                    ),
                    return_exceptions=True,
                )
                self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
                self.assertEqual((await store.account("111"))["available"], "5000")
