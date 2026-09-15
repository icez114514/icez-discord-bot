import tempfile
import unittest
from pathlib import Path
from poker.store import Store, Conflict


class HandPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_money_snapshot_and_time_bank_deadline_commit_together(self):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                for user in ("111", "222"):
                    await store.login(user)
                    await store.command(
                        "buy" + user,
                        "buy_in",
                        user_id=user,
                        table_id="t",
                        amount="2000",
                    )
                await store.command(
                    "start",
                    "start_hand",
                    hand_id="h",
                    table_id="t",
                    players=["111", "222"],
                    snapshot={"phase": "preflop"},
                )
                await store.command(
                    "bet",
                    "bet",
                    hand_id="h",
                    user_id="111",
                    amount="100",
                    expected_version=0,
                    snapshot={"phase": "preflop", "pot": "100"},
                )
                self.assertEqual((await store.hand("h"))["version"], 1)
                with self.assertRaises(Conflict):
                    await store.command(
                        "stale-bet",
                        "bet",
                        hand_id="h",
                        user_id="222",
                        amount="100",
                        expected_version=0,
                        snapshot={"pot": "200"},
                    )
                self.assertEqual((await store.account("222"))["in_flight"], "0")
                await store.command(
                    "action",
                    "action",
                    hand_id="h",
                    user_id="111",
                    opportunity_id="a",
                    expected_version=1,
                    now=100,
                )
                for n in range(4):
                    outcome = await store.command(
                        "bank" + str(n),
                        "time_bank",
                        hand_id="h",
                        user_id="111",
                        opportunity_id="a",
                        expected_version=2 + n,
                        now=120 + n * 5,
                    )
                    self.assertEqual(outcome["deadline"], 125 + n * 5)
                self.assertEqual((await store.account("111"))["time_bank"], 40)
                with self.assertRaises(Conflict):
                    await store.command(
                        "bank5",
                        "time_bank",
                        hand_id="h",
                        user_id="111",
                        opportunity_id="a",
                        now=140,
                    )
                self.assertEqual((await store.account("111"))["time_bank"], 40)
                replay = await store.command(
                    "bank3",
                    "time_bank",
                    hand_id="h",
                    user_id="111",
                    opportunity_id="a",
                    expected_version=5,
                    now=200,
                )
                self.assertEqual(replay["deadline"], 140)
